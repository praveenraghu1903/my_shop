from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Store, Product, Stock, Invoice, InvoiceItem, UserProfile, Supplier, Purchase, PurchaseItem, Location, InvoiceContact
from django.db.models import Sum
from django import forms
from decimal import Decimal

class ProductAdminForm(forms.ModelForm):
    """Custom form for Product admin that includes initial quantity and location setup"""
    initial_quantity = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text="Initial stock quantity to add to Central Godown (optional)"
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
        # If editing existing product, don't show initial quantity/location
        if self.instance and self.instance.pk:
            self.fields['initial_quantity'].widget = forms.HiddenInput()
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
            initial_location = form.cleaned_data.get('initial_location')

            if initial_quantity and initial_quantity > 0:
                # Get the central godown
                try:
                    godown = Store.objects.get(store_type='GODOWN')
                    # Create or update stock for this product in godown
                    stock, created = Stock.objects.get_or_create(
                        product=obj,
                        store=godown,
                        defaults={'quantity': initial_quantity}
                    )
                    if not created:
                        stock.quantity += initial_quantity
                        stock.save()
                except Store.DoesNotExist:
                    # If no godown exists, we can't create stock
                    pass

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

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'customer_phones', 'store', 'date', 'total_amount', 'paid_amount')
    list_filter = ('store', 'date')
    inlines = [InvoiceItemInline, InvoiceContactInline]

    def customer_phones(self, obj):
        others = ', '.join(c.mobile for c in obj.contacts.all())
        if obj.customer_mobile and others:
            return f"{obj.customer_mobile}, {others}"
        return obj.customer_mobile or others or ''
    customer_phones.short_description = 'Mobile Numbers'

admin.site.register(Supplier)
admin.site.register(Purchase)
admin.site.register(PurchaseItem)
admin.site.register(Location)

# Custom admin titles
admin.site.site_header = "AMBIKA"
admin.site.site_title = "AMBIKA Admin"
admin.site.index_title = "AMBIKA Dashboard"
