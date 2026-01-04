#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
python setup_initial_data.py
python setup_test_product.py

# Create or update superuser from env vars via a dedicated script
# Requires: DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_PASSWORD, optional DJANGO_SUPERUSER_EMAIL
python create_admin.py || true
