from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Store, Product, Stock, Invoice, InvoiceItem, UserProfile, Supplier, Purchase, PurchaseItem, Location, InvoiceContact, DueInvoice, ProductBuyPrice
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django import forms
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.http import HttpResponse

class ProductAdminForm(forms.ModelForm):
    """Custom form for Product admin that includes initial quantity, store and location setup"""
    initial_quantity = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text="Initial stock quantity to add (optional)"
    )
    initial_store = forms.ModelChoiceField(
        queryset=Store.objects.filter(store_type='GODOWN'),
        required=False,
        help_text="Godown/store where initial stock will be kept (optional)"
    )
    initial_location = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        help_text="Initial location to assign to this product (optional)"
    )

    class Meta:
        model = Product
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If editing existing product, don't show initial quantity/store/location
        if self.instance and self.instance.pk:
            self.fields['initial_quantity'].widget = forms.HiddenInput()
            self.fields['initial_store'].widget = forms.HiddenInput()
            self.fields['initial_location'].widget = forms.HiddenInput()

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'User Profile'

class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'store_type')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ('name', 'category', 'size', 'unit', 'total_stock', 'get_locations')
    list_filter = ('category', 'locations')
    search_fields = ('name', 'category', 'size')

    def get_locations(self, obj):
        return ', '.join(loc.name for loc in obj.locations.all()) or '-'
    get_locations.short_description = 'Locations'

    def save_model(self, request, obj, form, change):
        # Save the product first
        super().save_model(request, obj, form, change)

        # If this is a new product and initial_quantity is provided, create stock
        if not change:  # Only for new products
            initial_quantity = form.cleaned_data.get('initial_quantity')
            initial_store = form.cleaned_data.get('initial_store')
            initial_location = form.cleaned_data.get('initial_location')

            if initial_quantity and initial_quantity > 0:
                # Prefer the user-selected store; fall back to first GODOWN if not provided
                godown = initial_store or Store.objects.filter(store_type='GODOWN').first()
                if godown:
                    # Create or update stock for this product in selected godown
                    stock, created = Stock.objects.get_or_create(
                        product=obj,
                        store=godown,
                        defaults={'quantity': initial_quantity}
                    )
                    if not created:
                        stock.quantity += initial_quantity
                        stock.save()

            # If initial location is provided, add it to the product's locations
            if initial_location:
                obj.locations.add(initial_location)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(
            total_stock=Sum('stock__quantity'),
        )
        return qs

    def total_stock(self, obj):
        return obj.total_stock or 0
    total_stock.admin_order_field = 'total_stock'
    total_stock.short_description = 'Stock Qty (All)'

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    autocomplete_fields = ['product']
    list_display = ('product', 'store', 'quantity')
    list_filter = ('store',)
    search_fields = ('product__name', 'product__category', 'product__size', 'store__name')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "store":
            kwargs["queryset"] = Store.objects.filter(store_type='GODOWN')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fields = ('product', 'quantity', 'rate', 'location')

class InvoiceContactInline(admin.TabularInline):
    model = InvoiceContact
    extra = 0


class InvoiceAdminForm(forms.ModelForm):
    due_amount_paid = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal('0'),
        initial=Decimal('0'),
        label="Due amount paid",
        help_text="Enter the amount received now. This will be added to Paid Amount and reduce the due.",
    )

    class Meta:
        model = Invoice
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        due_amount_paid = cleaned.get('due_amount_paid') or Decimal('0')
        paid_amount = cleaned.get('paid_amount') or Decimal('0')
        total_amount = cleaned.get('total_amount') or Decimal('0')

        new_paid = paid_amount + due_amount_paid
        if new_paid > total_amount:
            raise ValidationError("Paid amount cannot exceed total amount.")
        return cleaned


class DueAmountFilter(admin.SimpleListFilter):
    title = "due amount"
    parameter_name = "due_amount"

    def lookups(self, request, model_admin):
        return (
            ("gt0", "Due > 0"),
            ("gte5000", "Due ≥ 5,000"),
            ("gte10000", "Due ≥ 10,000"),
        )

    def queryset(self, request, queryset):
        # relies on balance_due_annot added in get_queryset
        value = self.value()
        if value == "gt0":
            return queryset.filter(balance_due_annot__gt=0)
        if value == "gte5000":
            return queryset.filter(balance_due_annot__gte=5000)
        if value == "gte10000":
            return queryset.filter(balance_due_annot__gte=10000)
        return queryset

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    form = InvoiceAdminForm
    list_display = ('id', 'customer_name', 'customer_phones', 'store', 'date', 'total_amount', 'paid_amount', 'balance_due_display')
    list_filter = ('store', 'date', DueAmountFilter)
    search_fields = ('customer_name', 'customer_mobile', 'contacts__mobile')
    inlines = [InvoiceItemInline, InvoiceContactInline]
    readonly_fields = ('date',)
    actions = [
        'move_to_gairatganj',
        'move_to_silwani',
        'mark_fully_paid',
        'export_selected_csv',
    ]

    fieldsets = (
        (None, {
            'fields': ('store', 'customer_name', 'customer_mobile', 'date')
        }),
        ('Amounts', {
            'fields': (
                'total_amount',
                'discount_amount',
                'transport_cost',
                'transporter_name',
                'labour_cost',
                'other_expenses',
                'paid_amount',
                'due_amount_paid',
            )
        }),
    )

    def save_model(self, request, obj, form, change):
        due_amount_paid = form.cleaned_data.get('due_amount_paid') or Decimal('0')
        if due_amount_paid and due_amount_paid > 0:
            obj.paid_amount = (obj.paid_amount or Decimal('0')) + due_amount_paid
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        """
        Override to recalculate invoice total_amount when invoice items are added/modified/deleted.
        This fixes the issue where adding products to existing invoices doesn't update the total.

        Also keeps Godown Stock in sync with invoice item edits: increasing a line's
        quantity (or adding a new line) deducts the extra from stock, decreasing a
        line's quantity (or deleting a line) returns the difference to stock.
        """
        is_invoice_items = formset.model == InvoiceItem
        godown = None
        original_by_id = {}

        if is_invoice_items:
            godown = Store.objects.filter(store_type='GODOWN').first()
            # Snapshot original quantities/products BEFORE the formset touches anything,
            # since Django binds new POST values onto form.instance during validation.
            original_by_id = {
                row['id']: (row['product_id'], row['quantity'])
                for row in InvoiceItem.objects.filter(invoice=form.instance).values('id', 'product_id', 'quantity')
            }

        def adjust_stock(product, delta):
            """delta > 0 returns stock, delta < 0 deducts stock."""
            if not godown or not delta:
                return
            stock, _ = Stock.objects.get_or_create(product=product, store=godown, defaults={'quantity': Decimal('0')})
            stock.quantity += delta
            stock.save()
            if stock.quantity < 0:
                messages.warning(
                    request,
                    f"Warning: stock for '{product.name}' is now negative ({stock.quantity}) after this edit."
                )

        def adjust_stock_by_id(product_id, delta):
            if not godown or not delta:
                return
            stock, _ = Stock.objects.get_or_create(product_id=product_id, store=godown, defaults={'quantity': Decimal('0')})
            stock.quantity += delta
            stock.save()

        # Save the formset first (this saves all the invoice items)
        instances = formset.save(commit=False)

        # Handle deleted items — return their full quantity to stock
        for obj in formset.deleted_objects:
            if is_invoice_items:
                adjust_stock(obj.product, obj.quantity)
            obj.delete()

        # Save new/modified items — adjust stock by the quantity delta
        for instance in instances:
            if is_invoice_items:
                original = original_by_id.get(instance.pk)
                if original is None:
                    # Brand new line item: deduct full quantity from stock
                    adjust_stock(instance.product, -instance.quantity)
                else:
                    original_product_id, original_qty = original
                    if original_product_id != instance.product_id:
                        # Product on this line was swapped: return old product's qty,
                        # deduct new product's qty
                        adjust_stock_by_id(original_product_id, original_qty)
                        adjust_stock(instance.product, -instance.quantity)
                    else:
                        delta = instance.quantity - original_qty
                        adjust_stock(instance.product, -delta)
            instance.save()

        formset.save_m2m()

        # Now recalculate the invoice total based on all current items
        invoice = form.instance

        # Check if this is the InvoiceItem formset (not InvoiceContact)
        if is_invoice_items:
            # Calculate sum of all invoice items (quantity × rate)
            items_total = Decimal('0')
            for item in invoice.items.all():
                items_total += item.quantity * item.rate

            # Recalculate total_amount: items_total + transport + labour - discount
            invoice.total_amount = (
                items_total +
                (invoice.transport_cost or Decimal('0')) +
                (invoice.labour_cost or Decimal('0')) -
                (invoice.discount_amount or Decimal('0'))
            )
            invoice.save(update_fields=['total_amount'])

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            balance_due_annot=ExpressionWrapper(
                F('total_amount') - F('paid_amount'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )

    def customer_phones(self, obj):
        others = ', '.join(c.mobile for c in obj.contacts.all())
        if obj.customer_mobile and others:
            return f"{obj.customer_mobile}, {others}"
        return obj.customer_mobile or others or ''
    customer_phones.short_description = 'Mobile Numbers'

    def balance_due_display(self, obj):
        return obj.balance_due_annot

    balance_due_display.short_description = 'Balance Due'
    balance_due_display.admin_order_field = 'balance_due_annot'

    # ── Bulk Actions ─────────────────────────────────────────────────────

    def move_to_gairatganj(self, request, queryset):
        store = Store.objects.filter(name__icontains='gairatganj').first()
        if not store:
            self.message_user(request, "No store found matching 'Gairatganj'.", level='ERROR')
            return
        updated = queryset.update(store=store)
        self.message_user(request, f"{updated} invoice(s) moved to {store.name}.")
    move_to_gairatganj.short_description = "Move selected invoices to Gairatganj"

    def move_to_silwani(self, request, queryset):
        store = Store.objects.filter(name__icontains='silwani').first()
        if not store:
            self.message_user(request, "No store found matching 'Silwani'.", level='ERROR')
            return
        updated = queryset.update(store=store)
        self.message_user(request, f"{updated} invoice(s) moved to {store.name}.")
    move_to_silwani.short_description = "Move selected invoices to Silwani"

    def mark_fully_paid(self, request, queryset):
        updated = 0
        for invoice in queryset:
            if invoice.paid_amount != invoice.total_amount:
                invoice.paid_amount = invoice.total_amount
                invoice.save(update_fields=['paid_amount'])
                updated += 1
        self.message_user(request, f"{updated} invoice(s) marked as fully paid.")
    mark_fully_paid.short_description = "Mark selected invoices as fully paid"

    def export_selected_csv(self, request, queryset):
        import csv
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="invoices_export.csv"'
        writer = csv.writer(response)
        writer.writerow(['ID', 'Customer', 'Mobile', 'Store', 'Date', 'Total', 'Paid', 'Due'])
        for inv in queryset:
            writer.writerow([
                inv.id, inv.customer_name, inv.customer_mobile, inv.store.name,
                inv.date.strftime('%Y-%m-%d'), inv.total_amount, inv.paid_amount,
                inv.total_amount - inv.paid_amount,
            ])
        return response
    export_selected_csv.short_description = "Export selected invoices to CSV"

@admin.register(DueInvoice)
class DueInvoiceAdmin(InvoiceAdmin):
    """
    Separate admin section that shows only invoices where some money is still due.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(balance_due_annot__gt=0)

admin.site.register(Supplier)
admin.site.register(Purchase)
admin.site.register(PurchaseItem)
admin.site.register(Location)

# Custom admin titles
admin.site.site_header = "AMBIKA"
admin.site.site_title = "AMBIKA Admin"
admin.site.index_title = "AMBIKA Dashboard"


# ─────────────────────────────────────────────────────────────────────────────
# CASH FLOW — Custom admin URL, superuser only
# ─────────────────────────────────────────────────────────────────────────────

from django.urls import path
from django.http import HttpResponseForbidden
from django.template.response import TemplateResponse
from django.utils import timezone
import json
from datetime import date
from dateutil.relativedelta import relativedelta

def cashflow_view(request):
    """Full year cash flow & business analytics — superuser only."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied.")

    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))

    # ── All years available ────────────────────────────────────────────────
    from django.db.models import Min
    first_inv = Invoice.objects.aggregate(mn=Min('date'))['mn']
    first_year = first_inv.year if first_inv else today.year
    available_years = list(range(first_year, today.year + 1))

    # ── Month-by-month data for selected year ─────────────────────────────
    months_data = []
    year_revenue = Decimal('0')
    year_collected = Decimal('0')
    year_due = Decimal('0')
    year_purchases = Decimal('0')
    year_transport = Decimal('0')
    year_labour = Decimal('0')
    year_discounts = Decimal('0')
    year_invoices = 0

    for m in range(1, 13):
        m_start = date(year, m, 1)
        m_end = (m_start + relativedelta(months=1) - relativedelta(days=1))

        invs = Invoice.objects.filter(date__date__gte=m_start, date__date__lte=m_end)
        m_revenue   = invs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0')
        m_collected = invs.aggregate(s=Sum('paid_amount'))['s'] or Decimal('0')
        m_transport = invs.aggregate(s=Sum('transport_cost'))['s'] or Decimal('0')
        m_labour    = invs.aggregate(s=Sum('labour_cost'))['s'] or Decimal('0')
        m_discounts = invs.aggregate(s=Sum('discount_amount'))['s'] or Decimal('0')
        m_count     = invs.count()
        m_due       = m_revenue - m_collected

        purch = Purchase.objects.filter(date__date__gte=m_start, date__date__lte=m_end)
        m_purchases = purch.aggregate(s=Sum('total_amount'))['s'] or Decimal('0')

        m_expenses  = m_purchases + m_transport + m_labour
        m_net       = m_revenue - m_expenses

        months_data.append({
            'month': m_start.strftime('%b'),
            'revenue': float(m_revenue),
            'collected': float(m_collected),
            'due': float(m_due),
            'purchases': float(m_purchases),
            'transport': float(m_transport),
            'labour': float(m_labour),
            'discounts': float(m_discounts),
            'expenses': float(m_expenses),
            'net': float(m_net),
            'invoices': m_count,
        })

        year_revenue   += m_revenue
        year_collected += m_collected
        year_due       += m_due
        year_purchases += m_purchases
        year_transport += m_transport
        year_labour    += m_labour
        year_discounts += m_discounts
        year_invoices  += m_count

    year_expenses = year_purchases + year_transport + year_labour
    year_net      = year_revenue - year_expenses
    # Collection rate
    collection_rate = (float(year_collected) / float(year_revenue) * 100) if year_revenue > 0 else 0
    # Expense breakdown ratio
    purchase_pct   = (float(year_purchases) / float(year_expenses) * 100) if year_expenses > 0 else 0
    transport_pct  = (float(year_transport) / float(year_expenses) * 100) if year_expenses > 0 else 0
    labour_pct     = (float(year_labour)    / float(year_expenses) * 100) if year_expenses > 0 else 0

    # ── Store-wise breakdown ───────────────────────────────────────────────
    from django.db.models import Count
    stores = Store.objects.all()
    store_data = []
    for store in stores:
        sinvs = Invoice.objects.filter(
            date__year=year, store=store
        )
        s_rev  = sinvs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0')
        s_paid = sinvs.aggregate(s=Sum('paid_amount'))['s'] or Decimal('0')
        s_due  = s_rev - s_paid
        s_cnt  = sinvs.count()
        store_data.append({
            'name': store.name,
            'revenue': float(s_rev),
            'collected': float(s_paid),
            'due': float(s_due),
            'invoices': s_cnt,
        })

    # ── Top products by revenue ────────────────────────────────────────────
    from django.db.models import FloatField
    top_products = (
        InvoiceItem.objects
        .filter(invoice__date__year=year)
        .values('product__name', 'product__size', 'product__category')
        .annotate(
            total_qty=Sum('quantity'),
            total_rev=Sum(
                ExpressionWrapper(F('quantity') * F('rate'), output_field=DecimalField(max_digits=14, decimal_places=2))
            )
        )
        .order_by('-total_rev')[:10]
    )

    # ── Top customers by revenue ───────────────────────────────────────────
    top_customers = (
        Invoice.objects
        .filter(date__year=year)
        .values('customer_name', 'customer_mobile')
        .annotate(
            total_billed=Sum('total_amount'),
            total_paid=Sum('paid_amount'),
            invoice_count=Count('id')
        )
        .order_by('-total_billed')[:10]
    )

    # ── Outstanding dues (all time) ────────────────────────────────────────
    due_invoices = (
        Invoice.objects
        .annotate(bal=ExpressionWrapper(
            F('total_amount') - F('paid_amount'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        ))
        .filter(bal__gt=0)
        .order_by('-bal')[:20]
    )
    total_outstanding = Invoice.objects.annotate(
        bal=ExpressionWrapper(F('total_amount') - F('paid_amount'), output_field=DecimalField(max_digits=12, decimal_places=2))
    ).filter(bal__gt=0).aggregate(s=Sum('bal'))['s'] or Decimal('0')

    # ── Average invoice value ──────────────────────────────────────────────
    avg_invoice = (year_revenue / year_invoices) if year_invoices > 0 else Decimal('0')

    # ── Best and worst month ──────────────────────────────────────────────
    filled = [m for m in months_data if m['revenue'] > 0]
    best_month  = max(filled, key=lambda m: m['net'], default=None)
    worst_month = min(filled, key=lambda m: m['net'], default=None)

    context = {
        'year': year,
        'available_years': available_years,
        'today': today,

        # Year totals
        'year_revenue':    year_revenue,
        'year_collected':  year_collected,
        'year_due':        year_due,
        'year_purchases':  year_purchases,
        'year_transport':  year_transport,
        'year_labour':     year_labour,
        'year_discounts':  year_discounts,
        'year_expenses':   year_expenses,
        'year_net':        year_net,
        'year_invoices':   year_invoices,
        'collection_rate': round(collection_rate, 1),
        'avg_invoice':     avg_invoice,
        'purchase_pct':    round(purchase_pct, 1),
        'transport_pct':   round(transport_pct, 1),
        'labour_pct':      round(labour_pct, 1),
        'total_outstanding': total_outstanding,

        # Charts (JSON)
        'months_json':     json.dumps(months_data),
        'store_json':      json.dumps(store_data),

        # Tables
        'top_products':   top_products,
        'top_customers':  top_customers,
        'due_invoices':   due_invoices,
        'store_data':     store_data,
        'best_month':     best_month,
        'worst_month':    worst_month,

        'title': f'Cash Flow {year}',
    }
    return TemplateResponse(request, 'admin/cashflow.html', context)


# Monkey-patch admin site to add the cashflow URL
_original_get_urls = admin.site.__class__.get_urls

def _patched_get_urls(self):
    from django.contrib.admin.views.decorators import staff_member_required
    urls = _original_get_urls(self)
    extra = [
        path('cashflow/', self.admin_view(cashflow_view), name='cashflow'),
    ]
    return extra + urls

admin.site.__class__.get_urls = _patched_get_urls
