from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Store, Product, Stock, Invoice, InvoiceItem, UserProfile, Supplier, Purchase, PurchaseItem, Location, InvoiceContact, DueInvoice
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django import forms
from decimal import Decimal
from django.core.exceptions import ValidationError

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
