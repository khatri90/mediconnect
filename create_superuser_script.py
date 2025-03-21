import django
import os
import sys

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediconnect_project.settings')

# Initialize Django
django.setup()

from django.contrib.auth.models import User
from django.db import IntegrityError

# Check if superuser already exists
try:
    if User.objects.filter(is_superuser=True).exists():
        print('Superuser already exists')
    else:
        # Create superuser
        User.objects.create_superuser(
            username=os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin'),
            email=os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com'),
            password=os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'adminpassword')
        )
        print('Superuser created successfully')
except IntegrityError as e:
    print(f'Error creating superuser: {e}')