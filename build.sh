#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
python setup_initial_data.py
python setup_test_product.py

# Create superuser non-interactively if env vars are set on Render
# DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_PASSWORD, DJANGO_SUPERUSER_EMAIL
python manage.py createsuperuser --noinput || true
