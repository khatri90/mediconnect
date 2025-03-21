#!/bin/sh
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Create management command directory if it doesn't exist
mkdir -p doctors/management/commands

# Create admin user creation command
cat > doctors/management/commands/__init__.py << 'EOF'
# Initialize the management command package
EOF

cat > doctors/management/commands/create_admin.py << 'EOF'
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
import os

class Command(BaseCommand):
    help = 'Creates an admin user during build process'

    def handle(self, *args, **options):
        username = 'admin'
        email = 'admin@example.com'
        password = 'adminMediConnect123!'
        
        try:
            if User.objects.filter(username=username).exists():
                self.stdout.write(self.style.WARNING(f"Admin user '{username}' already exists"))
                # Update password for existing user
                admin = User.objects.get(username=username)
                admin.set_password(password)
                admin.save()
                self.stdout.write(self.style.SUCCESS(f"Admin password reset for '{username}'"))
            else:
                User.objects.create_superuser(username, email, password)
                self.stdout.write(self.style.SUCCESS(f"Admin user '{username}' created successfully"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error creating admin user: {str(e)}"))
EOF

# Collect static files
python manage.py collectstatic --no-input

# Run migrations
python manage.py migrate

# Create admin user
python manage.py create_admin

echo "Build completed successfully."
