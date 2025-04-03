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

# Create a SQL file to directly create the appointments table
echo "Creating appointments table directly..."
cat > create_appointment_table.sql << EOL
-- Create appointments table
CREATE TABLE IF NOT EXISTS doctors_appointment (
    id BIGSERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    patient_name VARCHAR(255) NOT NULL,
    patient_email VARCHAR(254) NOT NULL,
    patient_phone VARCHAR(20),
    appointment_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    package_type VARCHAR(20) NOT NULL,
    problem_description TEXT,
    transaction_number VARCHAR(100),
    amount DECIMAL(10,2),
    status VARCHAR(20) NOT NULL DEFAULT 'confirmed',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    doctor_notes TEXT,
    admin_notes TEXT,
    doctor_id BIGINT NOT NULL REFERENCES doctors_doctor(id),
    appointment_id VARCHAR(6) UNIQUE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS doctors_app_doctor__51c15d_idx ON doctors_appointment(doctor_id, appointment_date);
CREATE INDEX IF NOT EXISTS doctors_app_patient_29f9f5_idx ON doctors_appointment(patient_id, status);
CREATE INDEX IF NOT EXISTS doctors_app_appoint_a54061_idx ON doctors_appointment(appointment_date, start_time);

-- Create constraint
ALTER TABLE doctors_appointment DROP CONSTRAINT IF EXISTS unique_appointment_slot;
ALTER TABLE doctors_appointment ADD CONSTRAINT unique_appointment_slot UNIQUE (doctor_id, appointment_date, start_time);

-- Add migration entry to prevent Django from trying to create this table again
INSERT INTO django_migrations (app, name, applied) 
VALUES ('doctors', 'manual_appointment_creation', NOW())
ON CONFLICT DO NOTHING;
EOL

# Create a SQL file to directly create the reviews table
echo "Creating reviews table directly..."
cat > create_reviews_table.sql << EOL
-- Add average_rating and total_reviews fields to doctors_doctor table
ALTER TABLE doctors_doctor 
ADD COLUMN IF NOT EXISTS average_rating DECIMAL(3,2),
ADD COLUMN IF NOT EXISTS total_reviews INTEGER DEFAULT 0;

-- Create reviews table
CREATE TABLE IF NOT EXISTS doctors_review (
    id BIGSERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    review_text TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    appointment_id BIGINT NOT NULL REFERENCES doctors_appointment(id) ON DELETE CASCADE,
    doctor_id BIGINT NOT NULL REFERENCES doctors_doctor(id) ON DELETE CASCADE,
    CONSTRAINT unique_appointment_review UNIQUE (appointment_id, doctor_id, patient_id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS doctors_review_doctor_rating_idx ON doctors_review(doctor_id, rating);
CREATE INDEX IF NOT EXISTS doctors_review_patient_idx ON doctors_review(patient_id);

-- Add migration entry to prevent Django from trying to create this table again
INSERT INTO django_migrations (app, name, applied) 
VALUES ('doctors', 'manual_review_creation', NOW())
ON CONFLICT DO NOTHING;
EOL

# Execute the SQL file directly to create appointments table
echo "Executing SQL to create appointments table..."
python -c "
import os
import psycopg2

# Connect to the database
conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
conn.autocommit = True  # Set autocommit mode
cursor = conn.cursor()

# Read the SQL file
with open('create_appointment_table.sql', 'r') as f:
    sql = f.read()

# Execute the SQL
try:
    cursor.execute(sql)
    print('Appointments SQL executed successfully')
except Exception as e:
    print(f'Error executing SQL: {e}')
finally:
    cursor.close()
    conn.close()
"

# Execute the SQL file directly to create reviews table
echo "Executing SQL to create reviews table..."
python -c "
import os
import psycopg2

# Connect to the database
conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
conn.autocommit = True  # Set autocommit mode
cursor = conn.cursor()

# Read the SQL file
with open('create_reviews_table.sql', 'r') as f:
    sql = f.read()

# Execute the SQL
try:
    cursor.execute(sql)
    print('Reviews SQL executed successfully')
except Exception as e:
    print(f'Error executing SQL: {e}')
finally:
    cursor.close()
    conn.close()
"

# Mark all migrations as applied without running them
echo "Marking all migrations as applied without actually running them..."
python manage.py migrate --fake

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

# Add appointment_id column to appointments table and modify it to accept NULL values
echo "Adding/Modifying appointment_id column in appointments table..."
python -c "
import os
import psycopg2
import random
import time

def generate_hex_id(length=6):
    \"\"\"Generate a random hexadecimal ID of specified length\"\"\"
    hex_chars = '0123456789ABCDEF'
    return ''.join(random.choice(hex_chars) for _ in range(length))

# Connect to the database
conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
conn.autocommit = True  # Set autocommit mode
cursor = conn.cursor()

# Check if column exists
cursor.execute(\"\"\"
SELECT column_name 
FROM information_schema.columns 
WHERE table_name='doctors_appointment' AND column_name='appointment_id';
\"\"\")
column_exists = cursor.fetchone()

if not column_exists:
    # Add the column with NULL allowed
    try:
        cursor.execute(\"\"\"
        ALTER TABLE doctors_appointment 
        ADD COLUMN appointment_id VARCHAR(6) UNIQUE;
        \"\"\")
        print('Column appointment_id added successfully')
        
        # Get all existing appointments
        cursor.execute(\"\"\"
        SELECT id FROM doctors_appointment;
        \"\"\")
        appointments = cursor.fetchall()
        
        # Generate and set unique IDs for each existing appointment
        for appt_id in appointments:
            # Try up to 10 times to generate a unique ID
            for _ in range(10):
                new_id = generate_hex_id()
                # Check if this ID already exists
                cursor.execute(\"\"\"
                SELECT COUNT(*) FROM doctors_appointment 
                WHERE appointment_id = %s;
                \"\"\", (new_id,))
                if cursor.fetchone()[0] == 0:
                    # ID is unique, assign it to this appointment
                    cursor.execute(\"\"\"
                    UPDATE doctors_appointment 
                    SET appointment_id = %s 
                    WHERE id = %s;
                    \"\"\", (new_id, appt_id[0]))
                    print(f'Set appointment ID {new_id} for appointment {appt_id[0]}')
                    break
            else:
                # If we failed 10 times, use a timestamp-based approach
                timestamp = hex(int(time.time()))[2:]  # Convert timestamp to hex and remove '0x'
                new_id = f'{timestamp[-6:].upper()}{appt_id[0] % 10}'  # Use last 6 chars + record ID digit
                cursor.execute(\"\"\"
                UPDATE doctors_appointment 
                SET appointment_id = %s 
                WHERE id = %s;
                \"\"\", (new_id, appt_id[0]))
                print(f'Set timestamp-based ID {new_id} for appointment {appt_id[0]}')
    except Exception as e:
        print(f'Error working with appointment_id column: {e}')
else:
    # Column exists, modify it to allow NULL
    try:
        cursor.execute(\"\"\"
        ALTER TABLE doctors_appointment 
        ALTER COLUMN appointment_id DROP NOT NULL;
        \"\"\")
        print('Modified appointment_id column to allow NULL values')
    except Exception as e:
        print(f'Error modifying appointment_id column: {e}')

cursor.close()
conn.close()
"

# Create custom migration file for appointment_id field modification
echo "Creating custom migration file for appointment_id field..."
mkdir -p doctors/migrations
cat > doctors/migrations/0005_alter_appointment_appointment_id.py << EOL
# Generated by Django 5.1.7 on 2025-03-30 00:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('doctors', '0004_appointment_appointment_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appointment',
            name='appointment_id',
            field=models.CharField(blank=True, help_text='Unique 6-character hexadecimal ID', max_length=6, null=True, unique=True),
        ),
    ]
EOL

# Create custom migration file for review model
echo "Creating custom migration file for review model..."
cat > doctors/migrations/0006_doctor_rating_fields_review.py << EOL
# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('doctors', '0005_alter_appointment_appointment_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='doctor',
            name='average_rating',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=3, null=True),
        ),
        migrations.AddField(
            model_name='doctor',
            name='total_reviews',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='appointment',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending Confirmation'), ('confirmed', 'Confirmed'), ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('no_show', 'No Show')], default='confirmed', max_length=20),
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('patient_id', models.IntegerField()),
                ('rating', models.IntegerField(choices=[(1, '1 Star'), (2, '2 Stars'), (3, '3 Stars'), (4, '4 Stars'), (5, '5 Stars')])),
                ('review_text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('appointment', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='review', to='doctors.appointment')),
                ('doctor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='doctors.doctor')),
            ],
            options={
                'unique_together': {('appointment', 'doctor', 'patient_id')},
                'indexes': [models.Index(fields=['doctor', 'rating'], name='doctors_revi_doctor__5da7c0_idx'), models.Index(fields=['patient_id'], name='doctors_revi_patient_e33503_idx')],
            },
        ),
    ]
EOL

# Update models.py to allow blank and null values for appointment_id
echo "Updating models.py for appointment_id field..."
python -c "
import re

# Read the current models.py file
with open('doctors/models.py', 'r') as f:
    content = f.read()

# Replace the appointment_id field definition
new_content = re.sub(
    r'appointment_id = models\.CharField\([^)]*\)',
    'appointment_id = models.CharField(max_length=6, unique=True, blank=True, null=True, help_text=\"Unique 6-character hexadecimal ID\")',
    content
)

# Replace the default status for appointment
new_content = re.sub(
    r'status = models\.CharField\(max_length=20, choices=STATUS_CHOICES, default=\'pending\'\)',
    'status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=\'confirmed\')',
    new_content
)

# Write the updated content back
with open('doctors/models.py', 'w') as f:
    f.write(new_content)

print('Updated models.py successfully')
"

# Update serializers.py to make appointment_id read-only
echo "Updating serializers.py for appointment_id field..."
python -c "
import re

# Read the current serializers.py file
with open('doctors/serializers.py', 'r') as f:
    content = f.read()

# Check if AppointmentCreateSerializer already has read_only_fields
if 'class AppointmentCreateSerializer' in content:
    # If it has read_only_fields, ensure appointment_id is included
    if 'read_only_fields =' in content:
        # Update the existing read_only_fields
        new_content = re.sub(
            r'read_only_fields = \[([^\]]*)\]',
            lambda m: 'read_only_fields = [' + (m.group(1) + ', \'appointment_id\'' if 'appointment_id' not in m.group(1) else m.group(1)) + ']',
            content
        )
    else:
        # Add read_only_fields if it doesn't exist
        new_content = re.sub(
            r'(class AppointmentCreateSerializer\([^)]*\):.*?class Meta:.*?exclude = \[[^\]]*\])',
            r'\\1\n        read_only_fields = [\'appointment_id\']',
            content, 
            flags=re.DOTALL
        )
    
    # Write the updated content back
    with open('doctors/serializers.py', 'w') as f:
        f.write(new_content)
        
    print('Updated serializers.py successfully')
else:
    print('AppointmentCreateSerializer not found in serializers.py')
"

# Add ReviewSerializer to serializers.py
echo "Adding ReviewSerializer to serializers.py..."
python -c "
# Read the current serializers.py file
with open('doctors/serializers.py', 'r') as f:
    content = f.read()

# Define ReviewSerializer
review_serializer = '''
class ReviewSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    
    class Meta:
        model = Review
        fields = ['id', 'appointment', 'doctor', 'doctor_name', 'patient_id', 'rating', 
                 'review_text', 'created_at']
        read_only_fields = ['id', 'created_at', 'doctor_name']
'''

# Check if Review model is imported
if 'from .models import Review' not in content:
    # Add the import
    content = content.replace(
        'from .models import Doctor, DoctorDocument',
        'from .models import Doctor, DoctorDocument, Review'
    )

# Add ReviewSerializer to the end if it doesn't exist
if 'class ReviewSerializer' not in content:
    content += review_serializer

# Write the updated content back
with open('doctors/serializers.py', 'w') as f:
    f.write(content)

print('Added ReviewSerializer to serializers.py')
"

# Update URLs to include review endpoints
echo "Updating URLs to include review endpoints..."
python -c "
# Read the current urls.py file
with open('doctors/urls.py', 'r') as f:
    content = f.read()

# Add ReviewAPIView to imports if not already there
if 'ReviewAPIView' not in content:
    import_line = 'from .views import ('
    updated_imports = import_line + '\n    ReviewAPIView,'
    content = content.replace(import_line, updated_imports)

# Add review URLs to urlpatterns
urlpatterns_start = 'urlpatterns = ['
review_urls = '''
    # Review paths
    path('reviews/', ReviewAPIView.as_view(), name='reviews'),
    path('reviews/<str:appointment_id>/', ReviewAPIView.as_view(), name='appointment-review'),
'''

# Check if review paths already exist
if 'reviews/' not in content:
    # Find where dashboard paths are added
    dashboard_paths_index = content.find('# New dashboard paths')
    if dashboard_paths_index != -1:
        # Insert review paths before dashboard paths
        content = content[:dashboard_paths_index] + '    # Review paths\n    path(\'reviews/\', ReviewAPIView.as_view(), name=\'reviews\'),\n    path(\'reviews/<str:appointment_id>/\', ReviewAPIView.as_view(), name=\'appointment-review\'),\n\n' + content[dashboard_paths_index:]
    else:
        # If dashboard paths section not found, add after appointment paths
        appointment_paths_index = content.find('# Appointment paths')
        if appointment_paths_index != -1:
            # Find the end of the appointment paths section
            next_section = content.find('#', appointment_paths_index + 1)
            if next_section != -1:
                content = content[:next_section] + '    # Review paths\n    path(\'reviews/\', ReviewAPIView.as_view(), name=\'reviews\'),\n    path(\'reviews/<str:appointment_id>/\', ReviewAPIView.as_view(), name=\'appointment-review\'),\n\n' + content[next_section:]
            else:
                # If no next section, add at the end of urlpatterns
                content = content.replace(']', '    # Review paths\n    path(\'reviews/\', ReviewAPIView.as_view(), name=\'reviews\'),\n    path(\'reviews/<str:appointment_id>/\', ReviewAPIView.as_view(), name=\'appointment-review\'),\n]')

# Write the updated content back
with open('doctors/urls.py', 'w') as f:
    f.write(content)

print('Updated URLs to include review endpoints')
"

# Update admin.py to register the Review model
echo "Updating admin.py to register the Review model..."
python -c "
# Read the current admin.py file
with open('doctors/admin.py', 'r') as f:
    content = f.read()

# Add Review to imports if not already there
if 'from .models import Review' not in content:
    import_line = 'from .models import Doctor, DoctorDocument, DoctorAccount, DoctorAvailability, DoctorAvailabilitySettings'
    updated_imports = import_line + ', Review'
    content = content.replace(import_line, updated_imports)

# Add ReviewAdmin registration
review_admin = '''
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['appointment_id_display', 'doctor_name', 'patient_id', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['doctor__first_name', 'doctor__last_name', 'appointment__appointment_id', 'review_text']
    readonly_fields = ['created_at', 'updated_at']
    
    def appointment_id_display(self, obj):
        """Display appointment ID in a more readable format"""
        return obj.appointment.appointment_id if obj.appointment.appointment_id else f'#{obj.appointment.id}'
    appointment_id_display.short_description = 'Appointment'
    
    def doctor_name(self, obj):
        """Display doctor's full name"""
        return obj.doctor.full_name
    doctor_name.short_description = 'Doctor'
'''

# Check if ReviewAdmin already exists
if '@admin.register(Review)' not in content:
    # Add at the end of the file
    content += '\n' + review_admin

# Update DoctorAdmin to show ratings
if 'rating_display' not in content:
    # Find the list_display line in DoctorAdmin
    import re
    pattern = r'list_display = \[[^\]]*\]'
    match = re.search(pattern, content)
    if match:
        old_list_display = match.group(0)
        new_list_display = old_list_display.replace(
            'created_at\'', 
            'created_at\', \'rating_display\''
        )
        content = content.replace(old_list_display, new_list_display)
        
        # Add rating_display method to DoctorAdmin
        doctor_admin_end = '@admin.register(DoctorDocument)'
        rating_display_method = '''
    def rating_display(self, obj):
        """Display doctor's rating in a readable format"""
        if obj.average_rating is None:
            return "No ratings"
        return f"{obj.average_rating:.1f} ★ ({obj.total_reviews})"
    rating_display.short_description = "Rating"
    
'''
        content = content.replace(doctor_admin_end, rating_display_method + doctor_admin_end)

# Write the updated content back
with open('doctors/admin.py', 'w') as f:
    f.write(content)

print('Updated admin.py to register the Review model')
"

# Apply our specific migrations
echo "Applying migrations..."
python manage.py migrate doctors 0006_doctor_rating_fields_review

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Build completed successfully."