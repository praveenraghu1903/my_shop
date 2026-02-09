#!/usr/bin/env python
"""
Database Migration Script
Exports data from old Render DB and imports to new free DB
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tiles_automation.settings')
django.setup()

from django.core.management import call_command
from django.conf import settings
import subprocess

def export_data():
    """Export data from current database"""
    print("=" * 60)
    print("STEP 1: Exporting data from current database...")
    print("=" * 60)
    
    # Get current DATABASE_URL
    current_db = os.environ.get('DATABASE_URL')
    if not current_db:
        print("ERROR: DATABASE_URL not found in environment")
        return False
    
    print(f"Current database: {current_db[:50]}...")
    
    # Export using Django dumpdata
    backup_file = 'db_backup.json'
    try:
        print(f"Exporting to {backup_file}...")
        with open(backup_file, 'w') as f:
            call_command('dumpdata', '--natural-foreign', '--natural-primary', stdout=f, verbosity=1)
        print(f"✅ Data exported successfully to {backup_file}")
        return True
    except Exception as e:
        print(f"❌ Error exporting data: {e}")
        return False

def import_data(new_db_url):
    """Import data to new database"""
    print("\n" + "=" * 60)
    print("STEP 2: Importing data to new database...")
    print("=" * 60)
    
    # Temporarily set new DATABASE_URL
    os.environ['DATABASE_URL'] = new_db_url
    
    # Reconfigure Django database
    from django.conf import settings
    import dj_database_url
    settings.DATABASES['default'] = dj_database_url.config(default=new_db_url, conn_max_age=600)
    
    # Run migrations first
    print("Running migrations on new database...")
    try:
        call_command('migrate', verbosity=1, interactive=False)
        print("✅ Migrations completed")
    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        return False
    
    # Import data
    backup_file = 'db_backup.json'
    if not os.path.exists(backup_file):
        print(f"❌ Backup file {backup_file} not found!")
        return False
    
    try:
        print(f"Importing data from {backup_file}...")
        call_command('loaddata', backup_file, verbosity=1)
        print("✅ Data imported successfully!")
        return True
    except Exception as e:
        print(f"❌ Error importing data: {e}")
        return False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python migrate_database.py <NEW_DATABASE_URL>")
        print("\nExample:")
        print("  python migrate_database.py postgresql://user:pass@host:5432/dbname")
        print("\nOr run export only:")
        print("  python migrate_database.py export")
        sys.exit(1)
    
    if sys.argv[1] == 'export':
        export_data()
    else:
        new_db_url = sys.argv[1]
        if export_data():
            import_data(new_db_url)
            print("\n" + "=" * 60)
            print("✅ Migration completed successfully!")
            print("=" * 60)
            print("\nNext steps:")
            print("1. Update DATABASE_URL in Render web service environment variables")
            print("2. Restart your web service")
            print("3. Test your application")
        else:
            print("\n❌ Migration failed during export phase")
