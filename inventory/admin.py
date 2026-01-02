from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Store, Product, Stock, Invoice, InvoiceItem, UserProfile, Supplier, Purchase, PurchaseItem, Location, InvoiceContact
from django.db.models import Sum, Count, Max

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
    list_display = ('name', 'category', 'size', 'unit', 'total_stock', 'purchase_count', 'last_purchase_date')
    list_filter = ('category', 'locations')
    search_fields = ('name',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(
            total_stock=Sum('stock__quantity'),
            purchase_count=Count('purchaseitem', distinct=True),
            last_purchase_date=Max('purchaseitem__purchase__date'),
        )
        return qs

    def total_stock(self, obj):
        return obj.total_stock or 0
    total_stock.admin_order_field = 'total_stock'
    total_stock.short_description = 'Stock Qty (All)'

    def purchase_count(self, obj):
        return obj.purchase_count or 0
    purchase_count.admin_order_field = 'purchase_count'
    purchase_count.short_description = 'Times Purchased'

    def last_purchase_date(self, obj):
        return obj.last_purchase_date
    last_purchase_date.admin_order_field = 'last_purchase_date'
    last_purchase_date.short_description = 'Last Purchase'

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ('product', 'store', 'quantity')
    list_filter = ('store',)
    
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
