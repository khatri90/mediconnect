#!/bin/sh
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Debug database connection
echo "Database connection check..."
python -c "import os; import psycopg2; conn = psycopg2.connect(os.environ.get('DATABASE_URL')); print('Connection successful!'); conn.close()"

# Make migrations explicit for all apps to ensure they're created
echo "Making migrations for all apps..."
python manage.py makemigrations
python manage.py makemigrations admin auth contenttypes sessions rest_framework corsheaders doctors

# Apply migrations with verbosity
echo "Applying migrations..."
python manage.py migrate --noinput --verbosity 2

# Create admin user
echo "Creating admin user..."
python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediconnect_project.settings')
django.setup()
from django.contrib.auth.models import User
from django.db import connection

# Create tables directly if needed
with connection.cursor() as cursor:
    try:
        cursor.execute(\"\"\"
        SELECT 1 FROM pg_tables WHERE tablename = 'auth_user';
        \"\"\")
        if not cursor.fetchone():
            print('Creating auth_user table directly...')
            cursor.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS auth_user (
                id SERIAL PRIMARY KEY,
                password VARCHAR(128) NOT NULL,
                last_login TIMESTAMP WITH TIME ZONE NULL,
                is_superuser BOOLEAN NOT NULL,
                username VARCHAR(150) NOT NULL UNIQUE,
                first_name VARCHAR(150) NOT NULL,
                last_name VARCHAR(150) NOT NULL,
                email VARCHAR(254) NOT NULL,
                is_staff BOOLEAN NOT NULL,
                is_active BOOLEAN NOT NULL,
                date_joined TIMESTAMP WITH TIME ZONE NOT NULL
            );
            \"\"\")
            connection.commit()
    except Exception as e:
        print(f'Error checking/creating table: {e}')

# Create admin user
try:
    if User.objects.filter(username='admin').exists():
        admin = User.objects.get(username='admin')
        admin.set_password('MediConnect2025!')
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        print('Admin user updated')
    else:
        User.objects.create_superuser('admin', 'admin@example.com', 'MediConnect2025!')
        print('Admin user created')
except Exception as e:
    print(f'Error creating admin user: {e}')
"

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Build completed successfully."
