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

# Skip the admin.py update since it's already properly updated in your codebase

# Apply our specific migrations
echo "Applying migrations..."
python manage.py migrate --fake

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Build completed successfully."

# Add these lines to your build.sh file, right after the part that creates the reviews table

# Create a SQL file to directly create the support tables
echo "Creating support tables directly..."
cat > create_support_tables.sql << EOL
-- Create support_ticket table
CREATE TABLE IF NOT EXISTS doctors_supportticket (
    id BIGSERIAL PRIMARY KEY,
    ticket_id VARCHAR(10) UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL,
    subject VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    attachments VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'new',
    user_type VARCHAR(10) NOT NULL DEFAULT 'doctor',
    patient_id INTEGER,
    response TEXT,
    agent_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE,
    doctor_id BIGINT REFERENCES doctors_doctor(id) ON DELETE SET NULL
);

-- Create indexes for support_ticket
CREATE INDEX IF NOT EXISTS doctors_sup_ticket_idx ON doctors_supportticket(ticket_id);
CREATE INDEX IF NOT EXISTS doctors_sup_status_idx ON doctors_supportticket(status);
CREATE INDEX IF NOT EXISTS doctors_sup_doctor_idx ON doctors_supportticket(doctor_id);
CREATE INDEX IF NOT EXISTS doctors_sup_patient_idx ON doctors_supportticket(patient_id);

-- Create FAQ table
CREATE TABLE IF NOT EXISTS doctors_faq (
    id BIGSERIAL PRIMARY KEY,
    question VARCHAR(255) NOT NULL,
    answer TEXT NOT NULL,
    category VARCHAR(20) NOT NULL DEFAULT 'general',
    "order" INTEGER NOT NULL DEFAULT 0,
    is_published BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create index for FAQ ordering
CREATE INDEX IF NOT EXISTS doctors_faq_order_idx ON doctors_faq("order", category);

-- Add migration entry to prevent Django from trying to create these tables again
INSERT INTO django_migrations (app, name, applied) 
VALUES ('doctors', 'manual_support_creation', NOW())
ON CONFLICT DO NOTHING;

-- Insert initial FAQ data

EOL

# Execute the SQL file directly to create support tables
echo "Executing SQL to create support tables..."
python -c "
import os
import psycopg2

# Connect to the database
conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
conn.autocommit = True  # Set autocommit mode
cursor = conn.cursor()

# Read the SQL file
with open('create_support_tables.sql', 'r') as f:
    sql = f.read()

# Execute the SQL
try:
    cursor.execute(sql)
    print('Support tables SQL executed successfully')
except Exception as e:
    print(f'Error executing SQL: {e}')
finally:
    cursor.close()
    conn.close()
"
