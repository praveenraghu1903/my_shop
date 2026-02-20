import os
import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import F
from inventory.models import Invoice

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except Exception as e:
    service_account = None
    build = None


class Command(BaseCommand):
    help = 'Sync all invoices with due balance to a Google Sheet (daily run)'

    def add_arguments(self, parser):
        parser.add_argument('--sheet-name', type=str, help='Target sheet/tab name', default=None)
        parser.add_argument('--store', type=str, help='Filter by store name', default=None)

    def handle(self, *args, **options):
        if service_account is None or build is None:
            self.stderr.write('Google API libraries not installed. Ensure requirements are installed.')
            return

        creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        spreadsheet_id = os.environ.get('GOOGLE_SHEETS_SPREADSHEET_ID')
        sheet_name = options['sheet_name'] or os.environ.get('GOOGLE_SHEETS_DUE_SHEET_NAME', 'due_invoices')

        if not creds_json or not spreadsheet_id:
            self.stderr.write('Missing GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SHEETS_SPREADSHEET_ID environment variables.')
            return

        try:
            info = json.loads(creds_json)
            scopes = ['https://www.googleapis.com/auth/spreadsheets']
            creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
            service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
        except Exception as e:
            self.stderr.write(f'Failed to initialize Google Sheets client: {e}')
            return

        qs = Invoice.objects.select_related('store').prefetch_related('contacts').filter(total_amount__gt=F('paid_amount'))
        if options['store']:
            qs = qs.filter(store__name=options['store'])

        header = ['invoice_id', 'date', 'store', 'customer_name', 'phones', 'total', 'paid', 'due']
        values = [header]
        tz = timezone.get_current_timezone()
        for inv in qs.order_by('-date'):
            phones = []
            if inv.customer_mobile:
                phones.append(inv.customer_mobile)
            phones.extend([c.mobile for c in inv.contacts.all()])
            values.append([
                inv.id,
                inv.date.astimezone(tz).strftime('%Y-%m-%d %H:%M:%S'),
                inv.store.name,
                inv.customer_name,
                ', '.join([p for p in phones if p]),
                float(inv.total_amount),
                float(inv.paid_amount),
                float(inv.balance_due),
            ])

        # Ensure sheet exists; if clear fails, create it.
        clear_range = f'{sheet_name}!A:Z'
        try:
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=clear_range,
                body={}
            ).execute()
        except Exception:
            try:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={'requests': [{'addSheet': {'properties': {'title': sheet_name}}}]}
                ).execute()
            except Exception as e:
                self.stderr.write(f'Failed to create sheet "{sheet_name}": {e}')
                return

        try:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f'{sheet_name}!A1',
                valueInputOption='RAW',
                body={'values': values}
            ).execute()
        except Exception as e:
            self.stderr.write(f'Failed to write values: {e}')
            return

        self.stdout.write(self.style.SUCCESS(
            f'Synced {len(values)-1} due invoices to Google Sheet tab "{sheet_name}"'
        ))

