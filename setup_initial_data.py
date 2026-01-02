import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tiles_automation.settings")
django.setup()

from inventory.models import Store, UserProfile
from django.contrib.auth.models import User

stores = [
    {'name': 'Central Godown', 'type': 'GODOWN'},
    {'name': 'Silwani', 'type': 'DISPLAY'},
    {'name': 'Gairatganj', 'type': 'DISPLAY'},
]

for store_data in stores:
    store, created = Store.objects.get_or_create(name=store_data['name'], defaults={'store_type': store_data['type']})
    if created:
        print(f"Store '{store.name}' created.")

# Create Display User for Silwani
silwani_store = Store.objects.get(name='Silwani')
if not User.objects.filter(username='staff').exists():
    user = User.objects.create_user('staff', 'staff@example.com', 'staffpass')
    UserProfile.objects.create(user=user, store=silwani_store)
    print("User 'staff' created and linked to Silwani.")
else:
    print("User 'staff' already exists.")

# Create Display User for Gairatganj
gairatganj_store = Store.objects.get(name='Gairatganj')
if not User.objects.filter(username='staff_gairatganj').exists():
    user = User.objects.create_user('staff_gairatganj', 'staff_gairatganj@example.com', 'staffpass')
    UserProfile.objects.create(user=user, store=gairatganj_store)
    print("User 'staff_gairatganj' created and linked to Gairatganj.")
else:
    print("User 'staff_gairatganj' already exists.")

