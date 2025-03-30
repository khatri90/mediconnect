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
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    doctor_notes TEXT,
    admin_notes TEXT,
    doctor_id BIGINT NOT NULL REFERENCES doctors_doctor(id)
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

# Execute the SQL file directly
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
    print('SQL executed successfully')
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

# Add appointment_id column to appointments table and populate existing records
echo "Adding appointment_id column to appointments table..."
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
    # Add the column
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
    print('Column appointment_id already exists')

cursor.close()
conn.close()
"

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Build completed successfully."