from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Sum
from inventory.models import Product, InvoiceItem
import csv
from io import StringIO, BytesIO
import zipfile
from pathlib import Path


class Command(BaseCommand):
    help = 'Export daily inventory and sales report as a ZIP file under reports/'

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, help='Date in YYYY-MM-DD (default: today)')
        parser.add_argument('--out', type=str, help='Output directory (default: BASE_DIR/reports)')

    def handle(self, *args, **options):
        target_date = options.get('date')
        if target_date:
            try:
                day = timezone.datetime.strptime(target_date, '%Y-%m-%d').date()
            except Exception:
                self.stderr.write('Invalid date format, expected YYYY-MM-DD')
                return
        else:
            day = timezone.localdate()

        products = Product.objects.all().annotate(total_qty=Sum('stock__quantity'))
        inv_buf = StringIO()
        inv_writer = csv.writer(inv_buf)
        inv_writer.writerow(['product_id', 'name', 'size', 'category', 'unit', 'total_stock'])
        for p in products:
            inv_writer.writerow([p.id, p.name, p.size, p.get_category_display(), p.unit, p.total_qty or 0])

        items = (
            InvoiceItem.objects
            .filter(invoice__date__date=day)
            .select_related('invoice', 'product', 'invoice__store')
        )
        sales_buf = StringIO()
        sales_writer = csv.writer(sales_buf)
        sales_writer.writerow(['invoice_id', 'date', 'store', 'customer_name', 'product', 'quantity', 'rate', 'line_total', 'invoice_total', 'paid', 'due'])
        tz = timezone.get_current_timezone()
        for it in items:
            inv = it.invoice
            sales_writer.writerow([
                inv.id,
                inv.date.astimezone(tz).strftime('%Y-%m-%d %H:%M:%S'),
                inv.store.name,
                inv.customer_name,
                it.product.name,
                it.quantity,
                it.rate,
                it.item_total,
                inv.total_amount,
                inv.paid_amount,
                inv.balance_due,
            ])

        zip_bytes = BytesIO()
        with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f'inventory_{day}.csv', inv_buf.getvalue())
            zf.writestr(f'sales_{day}.csv', sales_buf.getvalue())
        zip_bytes.seek(0)

        out_dir = options.get('out')
        if out_dir:
            out_path = Path(out_dir)
        else:
            # BASE_DIR/../ since management command runs in project path, derive from settings
            from django.conf import settings
            out_path = Path(settings.BASE_DIR) / 'reports'
        out_path.mkdir(parents=True, exist_ok=True)
        file_path = out_path / f'daily_report_{day}.zip'
        with open(file_path, 'wb') as f:
            f.write(zip_bytes.read())

        self.stdout.write(self.style.SUCCESS(f'Report written to {file_path}'))

