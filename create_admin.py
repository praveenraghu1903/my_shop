import os
import sys

try:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tiles_automation.settings")
    import django
    django.setup()

    from django.contrib.auth import get_user_model

    User = get_user_model()
    username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
    email = os.environ.get("DJANGO_SUPERUSER_EMAIL") or (
        f"{username}@example.com" if username else None
    )

    if not username or not password:
        print(
            "Skipping superuser creation: missing DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD.",
        )
        sys.exit(0)

    user, created = User.objects.get_or_create(
        username=username, defaults={"email": email or "admin@example.com"}
    )
    user.is_staff = True
    user.is_superuser = True
    if email:
        user.email = email
    user.set_password(password)
    user.save()
    print(f"Admin user {username} created/updated successfully. created={created}")
    sys.exit(0)
except Exception as e:
    # Do not fail the build; just report the issue
    print(f"Admin creation script error: {e}")
    sys.exit(0)

