#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
python setup_initial_data.py
python setup_test_product.py

# Create or update superuser from env vars
# Requires: DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_PASSWORD, DJANGO_SUPERUSER_EMAIL
python manage.py shell -c "\
import os\
from django.contrib.auth import get_user_model\
User = get_user_model()\
username = os.environ.get('DJANGO_SUPERUSER_USERNAME')\
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')\
email = os.environ.get('DJANGO_SUPERUSER_EMAIL')\
if username and password:\
    if not email:\
        email = f"{username}@example.com"\
    user, created = User.objects.get_or_create(username=username, defaults={'email': email})\
    user.is_staff = True\
    user.is_superuser = True\
    user.email = email\
    user.set_password(password)\
    user.save()\
    print(f'Admin user {username} created/updated successfully.')\
else:\
    print('Skipping superuser creation: missing DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD.')\
" || true
