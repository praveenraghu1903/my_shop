from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import (
    Store, Product, Stock, Invoice, InvoiceItem, UserProfile,
    Supplier, Purchase, PurchaseItem, Location, InvoiceContact, DueInvoice,
    ProductBuyPrice
)
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django import forms
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.urls import path
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone
import json


# ─────────────────────────────────────────────────────────────────────────────
# ProductBuyPrice — SUPERUSER ONLY
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(ProductBuyPrice)
class ProductBuyPriceAdmin(admin.ModelAdmin):
    list_display = ('product', 'buy_price', 'updated_at')
    search_fields = ('product__name', 'product__size', 'product__category')
    autocomplete_fields = ['product']
    ordering = ('product__name',)

    def has_module_perms(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ─────────────────────────────────────────────────────────────────────────────
# Custom Admin Site with Cash Flow view
# ─────────────────────────────────────────────────────────────────────────────

class AmbikaAdminSite(admin.AdminSite):
    site_header = "AMBIKA"
    site_title = "AMBIKA Admin"
    index_title = "AMBIKA Dashboard"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('cashflow/', self.admin_view(self.cashflow_view), name='cashflow'),
        ]
        return custom_urls + urls

    def cashflow_view(self, request):
        """Balance sheet + cash flow analytics — superuser only."""
        if not request.user.is_superuser:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())

        from django.db.models import Q

        # ── Date range filter ──────────────────────────────────────────────
        today = timezone.now().date()
        range_param = request.GET.get('range', 'month')

        if range_param == 'week':
            from datetime import timedelta
            start_date = today - timedelta(days=6)
            range_label = "Last 7 Days"
        elif range_param == 'year':
            start_date = today.replace(month=1, day=1)
            range_label = f"Year {today.year}"
        else:  # month (default)
            start_date = today.replace(day=1)
            range_label = today.strftime("%B %Y")

        # ── Revenue (Sales) ───────────────────────────────────────────────
        invoices = Invoice.objects.filter(date__date__gte=start_date, date__date__lte=today)
        total_revenue = invoices.aggregate(s=Sum('total_amount'))['s'] or Decimal('0')
        total_collected = invoices.aggregate(s=Sum('paid_amount'))['s'] or Decimal('0')
        total_due = total_revenue - total_collected

        # ── Cost of Goods (using buy prices × invoice item quantities) ─────
        invoice_items = InvoiceItem.objects.filter(
            invoice__date__date__gte=start_date,
            invoice__date__date__lte=today
        ).select_related('product', 'product__buy_price_record')

        cogs = Decimal('0')
        for item in invoice_items:
            try:
                bp = item.product.buy_price_record.buy_price
                cogs += bp * item.quantity
            except ProductBuyPrice.DoesNotExist:
                pass

        # ── Purchase Expenses (goods bought from suppliers) ────────────────
        purchases = Purchase.objects.filter(date__date__gte=start_date, date__date__lte=today)
        total_purchases = purchases.aggregate(s=Sum('total_amount'))['s'] or Decimal('0')

        # ── Additional costs on invoices ──────────────────────────────────
        transport = invoices.aggregate(s=Sum('transport_cost'))['s'] or Decimal('0')
        labour = invoices.aggregate(s=Sum('labour_cost'))['s'] or Decimal('0')
        discounts = invoices.aggregate(s=Sum('discount_amount'))['s'] or Decimal('0')

        # ── Gross & Net ───────────────────────────────────────────────────
        gross_profit = total_revenue - cogs
        total_expenses = cogs + transport + labour
        net_profit = total_revenue - total_expenses

        # ── Monthly trend (last 6 months) ─────────────────────────────────
        from dateutil.relativedelta import relativedelta
        months_labels = []
        months_revenue = []
        months_expenses = []
        months_net = []

        for i in range(5, -1, -1):
            m_start = (today.replace(day=1) - relativedelta(months=i))
            m_end = (m_start + relativedelta(months=1) - relativedelta(days=1))
            months_labels.append(m_start.strftime("%b %y"))

            m_rev = Invoice.objects.filter(
                date__date__gte=m_start, date__date__lte=m_end
            ).aggregate(s=Sum('total_amount'))['s'] or Decimal('0')

            m_purchases = Purchase.objects.filter(
                date__date__gte=m_start, date__date__lte=m_end
            ).aggregate(s=Sum('total_amount'))['s'] or Decimal('0')

            m_items = InvoiceItem.objects.filter(
                invoice__date__date__gte=m_start,
                invoice__date__date__lte=m_end
            ).select_related('product__buy_price_record')
            m_cogs = Decimal('0')
            for it in m_items:
                try:
                    m_cogs += it.product.buy_price_record.buy_price * it.quantity
                except ProductBuyPrice.DoesNotExist:
                    pass

            months_revenue.append(float(m_rev))
            months_expenses.append(float(m_cogs + m_purchases))
            months_net.append(float(m_rev - m_cogs))

        # ── Category-wise revenue ─────────────────────────────────────────
        cat_data = {}
        for item in invoice_items:
            cat = item.product.get_category_display()
            cat_data[cat] = cat_data.get(cat, Decimal('0')) + item.quantity * item.rate

        # ── All due invoices (assets = money owed to us) ──────────────────
        due_invoices = Invoice.objects.annotate(
            bal=ExpressionWrapper(
                F('total_amount') - F('paid_amount'),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        ).filter(bal__gt=0).order_by('-date')[:20]

        context = {
            # Summaries
            'range_label': range_label,
            'range_param': range_param,
            'total_revenue': total_revenue,
            'total_collected': total_collected,
            'total_due': total_due,
            'cogs': cogs,
            'total_purchases': total_purchases,
            'transport': transport,
            'labour': labour,
            'discounts': discounts,
            'gross_profit': gross_profit,
            'net_profit': net_profit,
            'total_expenses': total_expenses,

            # Charts (JSON for JS)
            'months_labels_json': json.dumps(months_labels),
            'months_revenue_json': json.dumps(months_revenue),
            'months_expenses_json': json.dumps(months_expenses),
            'months_net_json': json.dumps(months_net),
            'cat_labels_json': json.dumps(list(cat_data.keys())),
            'cat_values_json': json.dumps([float(v) for v in cat_data.values()]),

            # Due invoices table
            'due_invoices': due_invoices,
            'opts': {},
            'title': 'Cash Flow & Balance Sheet',
        }
        return TemplateResponse(request, 'admin/cashflow.html', context)


# Replace default admin site
admin_site = AmbikaAdminSite(name='admin')


# ─────────────────────────────────────────────────────────────────────────────
# Standard model admins
# ─────────────────────────────────────────────────────────────────────────────

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
    list_display = ('name', 'category', 'size', 'unit', 'total_stock')
    list_filter = ('category', 'locations')
    search_fields = ('name', 'category', 'size')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            initial_quantity = form.cleaned_data.get('initial_quantity')
            initial_store = form.cleaned_data.get('initial_store')
            initial_location = form.cleaned_data.get('initial_location')

            if initial_quantity and initial_quantity > 0:
                godown = initial_store or Store.objects.filter(store_type='GODOWN').first()
                if godown:
                    stock, created = Stock.objects.get_or_create(
                        product=obj,
                        store=godown,
                        defaults={'quantity': initial_quantity}
                    )
                    if not created:
                        stock.quantity += initial_quantity
                        stock.save()

            if initial_location:
                obj.locations.add(initial_location)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(total_stock=Sum('stock__quantity'))
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

    fieldsets = (
        (None, {
            'fields': ('store', 'customer_name', 'customer_mobile', 'date')
        }),
        ('Amounts', {
            'fields': (
                'total_amount',
                'discount_amount',
                'transport_cost',
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
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            instance.save()
        formset.save_m2m()

        invoice = form.instance
        if formset.model == InvoiceItem:
            items_total = Decimal('0')
            for item in invoice.items.all():
                items_total += item.quantity * item.rate
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


@admin.register(DueInvoice)
class DueInvoiceAdmin(InvoiceAdmin):
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
