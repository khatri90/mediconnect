#!/bin/sh
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Install Pillow for image processing
pip install Pillow

# Debug database connection
echo "Database connection check..."
python -c "import os; import psycopg2; conn = psycopg2.connect(os.environ.get('DATABASE_URL')); print('Connection successful!'); conn.close()"

# Create placeholder image directory
mkdir -p staticfiles
mkdir -p media/doctor_documents

# Generate a simple placeholder image using Python
python -c '
from PIL import Image, ImageDraw
import os

# Create a directory for the placeholder images
os.makedirs("staticfiles", exist_ok=True)

# Create a simple colored rectangle as a placeholder
img = Image.new("RGB", (800, 600), color=(240, 248, 255))
d = ImageDraw.Draw(img)
d.rectangle([(0, 0), (800, 600)], outline=(0, 123, 255), width=20)
img.save("staticfiles/placeholder.jpg")

# Also save directly to media directory
os.makedirs("media/doctor_documents", exist_ok=True)
img.save("media/doctor_documents/background.jpg")
'

# Find the latest migration and create our custom migration for the Appointment model
python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediconnect_project.settings')
django.setup()

import glob
from django.db import migrations, models
import django.db.models.deletion

# Find the latest migration
migration_files = glob.glob('doctors/migrations/[0-9]*.py')
latest_migration = None
latest_number = -1

for file in migration_files:
    filename = os.path.basename(file)
    parts = filename.split('_')
    if len(parts) > 0:
        try:
            number = int(parts[0])
            if number > latest_number:
                latest_number = number
                latest_migration = filename.replace('.py', '')
        except ValueError:
            continue

if latest_migration is None:
    print('No existing migrations found, will create initial migration')
    latest_migration = 'initial'

# Create our custom migration for the Appointment model
next_number = latest_number + 1
next_migration = f'{next_number:04d}_appointment'
print(f'Creating migration {next_migration} with dependency on {latest_migration}')

migration_code = f'''
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('doctors', '{latest_migration}'),
    ]

    operations = [
        migrations.CreateModel(
            name='Appointment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('patient_id', models.IntegerField()),
                ('patient_name', models.CharField(max_length=255)),
                ('patient_email', models.EmailField(max_length=254)),
                ('patient_phone', models.CharField(blank=True, max_length=20, null=True)),
                ('appointment_date', models.DateField()),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('package_type', models.CharField(choices=[('in_person', 'In Person'), ('online', 'Online Consultation')], default='in_person', max_length=20)),
                ('problem_description', models.TextField(blank=True, null=True)),
                ('transaction_number', models.CharField(blank=True, max_length=100, null=True)),
                ('amount', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending Confirmation'), ('confirmed', 'Confirmed'), ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('no_show', 'No Show')], default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('doctor_notes', models.TextField(blank=True, null=True)),
                ('admin_notes', models.TextField(blank=True, null=True)),
                ('doctor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='appointments', to='doctors.doctor')),
            ],
            options={{
                'indexes': [models.Index(fields=['doctor', 'appointment_date'], name='doctors_app_doctor__51c15d_idx'), models.Index(fields=['patient_id', 'status'], name='doctors_app_patient_29f9f5_idx'), models.Index(fields=['appointment_date', 'start_time'], name='doctors_app_appoint_a54061_idx')],
            }},
        ),
        migrations.AddConstraint(
            model_name='appointment',
            constraint=models.UniqueConstraint(fields=('doctor', 'appointment_date', 'start_time'), name='unique_appointment_slot'),
        ),
    ]
'''

migration_path = f'doctors/migrations/{next_migration}.py'
with open(migration_path, 'w') as f:
    f.write(migration_code)

print(f'Created migration file: {migration_path}')
"

# Apply migrations with --fake-initial to avoid duplicate table errors
echo "Applying migrations..."
python manage.py migrate --fake-initial --noinput

# Create admin user
echo "Creating admin user..."
python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediconnect_project.settings')
django.setup()
from django.contrib.auth.models import User
from django.db import connection

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
