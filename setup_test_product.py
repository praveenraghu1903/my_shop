import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tiles_automation.settings")
django.setup()

from inventory.models import Store, Product, Stock

godown = Store.objects.filter(store_type='GODOWN').first()
if godown:
    product, _ = Product.objects.get_or_create(name='Test Tile 2x2', size='2x2', defaults={'category': 'TILES'})
    stock, created = Stock.objects.get_or_create(product=product, store=godown, defaults={'quantity': 1000})
    if not created:
        stock.quantity = 1000
        stock.save()
    
    print(f"Product '{product.name}' created/updated with {stock.quantity} sqft in Godown.")
else:
    print("Godown not found!")
