from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    store = models.ForeignKey('Store', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.store.name if self.store else 'No Store'}"

class Store(models.Model):
    STORE_TYPES = (
        ('DISPLAY', 'Display Shop'),
        ('GODOWN', 'Central Godown'),
    )
    name = models.CharField(max_length=100)
    store_type = models.CharField(max_length=20, choices=STORE_TYPES)

    def __str__(self):
        return f"{self.name} ({self.get_store_type_display()})"

class Product(models.Model):
    CATEGORY_CHOICES = (
        ('TILES', 'Tiles'),
        ('MARBLE', 'Marble'),
        ('GRANITE', 'Granite'),
        ('SANITARY', 'Sanitary'),
        ('OTHER', 'Other'),
    )
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='TILES')
    size = models.CharField(max_length=50, help_text="e.g., 2x2, 7x4")
    unit = models.CharField(max_length=20, default='sqft')
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    # Optional: multiple physical locations where this product can be found
    # Admin can assign one or more locations to a product
    # Used to select source location in invoice items
    # Note: locations are independent of Store/Godown stock tracking
    # and serve as logistics metadata for finding items physically
    # (e.g., "Front Display Rack", "Back Godown Shelf A2").
    
    # Declared below Location model; using string reference here to avoid re-ordering
    locations = models.ManyToManyField('Location', blank=True, related_name='products')

    def __str__(self):
        return f"{self.name} - {self.size}"

class Stock(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('product', 'store')

    def clean(self):
        if self.store.store_type != 'GODOWN':
            raise ValidationError("Stock can only be maintained for the Central Godown.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - {self.quantity} {self.product.unit} in {self.store.name}"

class Invoice(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, help_text="Store where sale happened")
    customer_name = models.CharField(max_length=100)
    customer_mobile = models.CharField(max_length=15, blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount

    def __str__(self):
        return f"Invoice #{self.id} - {self.customer_name}"

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    # Optional: physical location from which this item was picked
    location = models.ForeignKey('Location', on_delete=models.SET_NULL, null=True, blank=True)
    
    @property
    def item_total(self):
        return self.quantity * self.rate

    def __str__(self):
        return f"{self.product.name} ({self.quantity})"

class Location(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.name

class InvoiceContact(models.Model):
    invoice = models.ForeignKey(Invoice, related_name='contacts', on_delete=models.CASCADE)
    mobile = models.CharField(max_length=15)

    def __str__(self):
        return self.mobile

class Supplier(models.Model):
    name = models.CharField(max_length=100)
    contact = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Purchase(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True)
    date = models.DateTimeField(auto_now_add=True)
    invoice_number = models.CharField(max_length=50, blank=True, help_text="Supplier's Invoice Number")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    def __str__(self):
        return f"Purchase #{self.id} - {self.supplier.name if self.supplier else 'Unknown'}"

class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Purchase Rate")
    
    @property
    def item_total(self):
        return self.quantity * self.rate

    def __str__(self):
        return f"{self.product.name} ({self.quantity})"
