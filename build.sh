#!/bin/sh
# exit on error
set -o errexit

echo "Starting build process..."

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Install Pillow for image processing
pip install Pillow

# Debug database connection
echo "Database connection check..."
python -c "import os; import psycopg2; conn = psycopg2.connect(os.environ.get('DATABASE_URL')); print('Connection successful!'); conn.close()"

# Create placeholder image directory
mkdir -p staticfiles
mkdir -p media/doctor_documents
mkdir -p media/patient_documents
mkdir -p media/hospitals

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
os.makedirs("media/patient_documents", exist_ok=True)
os.makedirs("media/hospitals", exist_ok=True)
img.save("media/doctor_documents/background.jpg")
'

# Create a content type registration script
echo "Creating content type registration script..."
cat > register_content_types.py << EOL
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediconnect_project.settings')
django.setup()

from django.contrib.contenttypes.models import ContentType
from django.db import connection

# Make sure all patient models are registered
content_types = [
    {'app_label': 'patients', 'model': 'patient'},
    {'app_label': 'patients', 'model': 'patientaccount'},
    {'app_label': 'patients', 'model': 'medicalrecord'},
    {'app_label': 'patients', 'model': 'patientdocument'},
]

print("Registering content types for patients app...")
for ct in content_types:
    ContentType.objects.get_or_create(**ct)
    print(f"Registered {ct['app_label']}.{ct['model']}")

# Verify patient permissions in auth_permission table
cursor = connection.cursor()
sql = """
INSERT INTO auth_permission (name, content_type_id, codename)
SELECT 
    'Can view patient', 
    ct.id, 
    'view_patient'
FROM 
    django_content_type ct
WHERE 
    ct.app_label = 'patients' AND ct.model = 'patient'
AND NOT EXISTS (
    SELECT 1 FROM auth_permission 
    WHERE content_type_id = ct.id AND codename = 'view_patient'
);
"""
cursor.execute(sql)
print(f"Added missing permissions. Rows affected: {cursor.rowcount}")

# Add other CRUD permissions
for action in ['add', 'change', 'delete']:
    action_sql = f"""
    INSERT INTO auth_permission (name, content_type_id, codename)
    SELECT 
        'Can {action} patient', 
        ct.id, 
        '{action}_patient'
    FROM 
        django_content_type ct
    WHERE 
        ct.app_label = 'patients' AND ct.model = 'patient'
    AND NOT EXISTS (
        SELECT 1 FROM auth_permission 
        WHERE content_type_id = ct.id AND codename = '{action}_patient'
    );
    """
    cursor.execute(action_sql)
    print(f"Added {action} permission. Rows affected: {cursor.rowcount}")

cursor.close()

print("Done! Content types and permissions have been properly registered.")
EOL

# Create SQL files for the original doctor app tables
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
INSERT INTO doctors_faq (question, answer, category, "order", is_published)
VALUES
    ('How do I reschedule an appointment?', 
     'You can reschedule an appointment through the Appointments section of your dashboard. Simply locate the appointment you wish to reschedule, click the "Reschedule" button, and select a new available time slot.',
     'appointments', 1, TRUE),
     
    ('How do I update my billing information?', 
     'To update your billing information, go to your user profile and select the "Billing" tab. From there, you can add, remove, or update payment methods and view your billing history.',
     'billing', 1, TRUE),
     
    ('Can I download my medical records?', 
     'Yes, you can download your medical records from the Health Records section of your dashboard. Select the records you want to download and click the "Export" button. Files are available in PDF format.',
     'general', 1, TRUE),
     
    ('How do I share my health data with my doctor?', 
     'You can share your health data with your doctor by going to your profile and selecting "Share Profile." Enter your doctor''s email address or select them from your contacts list, then choose which data you want to share and for how long.',
     'general', 2, TRUE),
     
    ('What should I do if I encounter a technical issue?', 
     'If you encounter a technical issue, first try refreshing the page or logging out and back in. If the problem persists, please contact our technical support team through the Contact Support form, providing as much detail as possible about the issue.',
     'technical', 1, TRUE),
     
    ('How can I change my password?', 
     'To change your password, go to your profile settings and select "Change Password." You''ll need to enter your current password and then create a new one. For security, choose a strong password with a mix of letters, numbers, and special characters.',
     'account', 1, TRUE),
     
    ('Can I use the platform on my mobile device?', 
     'Yes, our platform is fully responsive and works on all mobile devices. You can also download our mobile app for iOS and Android for an optimized experience.',
     'technical', 2, TRUE),
     
    ('How do I cancel an appointment?', 
     'To cancel an appointment, go to the Appointments section of your dashboard, find the appointment you wish to cancel, and click the "Cancel" button. Please note that cancellations within 24 hours of the appointment may incur a fee.',
     'appointments', 2, TRUE),
     
    ('What payment methods are accepted?', 
     'We accept all major credit cards (Visa, MasterCard, American Express, Discover), PayPal, and bank transfers. Payment information is securely stored and processed.',
     'billing', 2, TRUE),
     
    ('How is my data protected?', 
     'We take data security seriously. All data is encrypted both in transit and at rest using industry-standard encryption. We comply with HIPAA regulations and employ strict access controls. You can review our full privacy policy for more details.',
     'privacy', 1, TRUE)
ON CONFLICT DO NOTHING;
EOL

# Create SQL files for the new app tables
echo "Creating patients tables directly..."
cat > create_patients_tables.sql << EOL
-- Create patients table
CREATE TABLE IF NOT EXISTS patients_patient (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    phone_number VARCHAR(15),
    dob DATE NOT NULL,
    gender VARCHAR(1) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_staff BOOLEAN NOT NULL DEFAULT FALSE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    date_joined TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    allergies TEXT,
    medical_conditions TEXT,
    medications TEXT,
    blood_type VARCHAR(5),
    password VARCHAR(128),
    last_login TIMESTAMP WITH TIME ZONE
);

-- Create patient account table
CREATE TABLE IF NOT EXISTS patients_patientaccount (
    id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT NOT NULL REFERENCES patients_patient(id) ON DELETE CASCADE,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    last_login TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create medical record table
CREATE TABLE IF NOT EXISTS patients_medicalrecord (
    id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT NOT NULL REFERENCES patients_patient(id) ON DELETE CASCADE,
    doctor_name VARCHAR(255) NOT NULL,
    doctor_id INTEGER,
    record_date DATE NOT NULL,
    diagnosis TEXT NOT NULL,
    treatment TEXT NOT NULL,
    prescription TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create patient document table
CREATE TABLE IF NOT EXISTS patients_patientdocument (
    id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT NOT NULL REFERENCES patients_patient(id) ON DELETE CASCADE,
    document_type VARCHAR(30) NOT NULL,
    title VARCHAR(255) NOT NULL,
    file VARCHAR(100) NOT NULL,
    notes TEXT,
    uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS patients_pat_email_idx ON patients_patient(email);
CREATE INDEX IF NOT EXISTS patients_pat_acc_patient_idx ON patients_patientaccount(patient_id);
CREATE INDEX IF NOT EXISTS patients_med_rec_patient_idx ON patients_medicalrecord(patient_id);
CREATE INDEX IF NOT EXISTS patients_med_rec_date_idx ON patients_medicalrecord(record_date);
CREATE INDEX IF NOT EXISTS patients_doc_patient_idx ON patients_patientdocument(patient_id);
CREATE INDEX IF NOT EXISTS patients_doc_type_idx ON patients_patientdocument(document_type);

-- Add migration entry to prevent Django from trying to create these tables again
INSERT INTO django_migrations (app, name, applied) 
VALUES ('patients', 'manual_patients_creation', NOW())
ON CONFLICT DO NOTHING;
EOL

echo "Creating hospitals tables directly..."
cat > create_hospitals_tables.sql << EOL
-- Create hospitals table
CREATE TABLE IF NOT EXISTS hospitals_hospital (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(255) NOT NULL,
    location TEXT,
    about TEXT,
    specialties TEXT,
    email VARCHAR(254),
    phone VARCHAR(20),
    website VARCHAR(200),
    main_image VARCHAR(100),
    thumbnail VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create departments table
CREATE TABLE IF NOT EXISTS hospitals_department (
    id BIGSERIAL PRIMARY KEY,
    hospital_id BIGINT NOT NULL REFERENCES hospitals_hospital(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    head_doctor VARCHAR(255),
    contact_email VARCHAR(254),
    contact_phone VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_department_name UNIQUE (hospital_id, name)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS hospitals_hosp_name_idx ON hospitals_hospital(name);
CREATE INDEX IF NOT EXISTS hospitals_hosp_city_idx ON hospitals_hospital(city);
CREATE INDEX IF NOT EXISTS hospitals_dept_hospital_idx ON hospitals_department(hospital_id);

-- Add migration entry to prevent Django from trying to create these tables again
INSERT INTO django_migrations (app, name, applied) 
VALUES ('hospitals', 'manual_hospitals_creation', NOW())
ON CONFLICT DO NOTHING;
EOL

# Execute SQL files to create all tables
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

echo "Executing SQL to create patients tables..."
python -c "
import os
import psycopg2

# Connect to the database
conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
conn.autocommit = True  # Set autocommit mode
cursor = conn.cursor()

# Read the SQL file
with open('create_patients_tables.sql', 'r') as f:
    sql = f.read()

# Execute the SQL
try:
    cursor.execute(sql)
    print('Patients tables SQL executed successfully')
except Exception as e:
    print(f'Error executing SQL: {e}')
finally:
    cursor.close()
    conn.close()
"

# Add is_superuser column to patients_patient table if it doesn't exist
echo "Adding is_superuser column to patients_patient table if it doesn't exist..."
python -c "
import os
import psycopg2

# Connect to the database
conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
conn.autocommit = True  # Set autocommit mode
cursor = conn.cursor()

# Check if column exists
try:
    cursor.execute(\"\"\"
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name='patients_patient' AND column_name='is_superuser';
    \"\"\")
    column_exists = cursor.fetchone()
    
    if not column_exists:
        cursor.execute(\"\"\"
        ALTER TABLE patients_patient ADD COLUMN is_superuser BOOLEAN NOT NULL DEFAULT FALSE;
        \"\"\")
        print('Column is_superuser added successfully to patients_patient table')
    else:
        print('Column is_superuser already exists in patients_patient table')
except Exception as e:
    print(f'Error checking/adding is_superuser column: {e}')
finally:
    cursor.close()
    conn.close()
"

echo "Executing SQL to create hospitals tables..."
python -c "
import os
import psycopg2

# Connect to the database
conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
conn.autocommit = True  # Set autocommit mode
cursor = conn.cursor()

# Read the SQL file
with open('create_hospitals_tables.sql', 'r') as f:
    sql = f.read()

# Execute the SQL
try:
    cursor.execute(sql)
    print('Hospitals tables SQL executed successfully')
except Exception as e:
    print(f'Error executing SQL: {e}')
finally:
    cursor.close()
    conn.close()
"

# Mark all migrations as applied without running them
echo "Marking all migrations as applied without actually running them..."
python manage.py migrate --fake

# Run the content type registration script
echo "Registering content types and permissions..."
python register_content_types.py

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

# Apply our specific migrations
echo "Applying migrations..."
python manage.py migrate --fake

# Register new apps in Django if they don't exist
echo "Registering new apps in Django..."
python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediconnect_project.settings')
django.setup()
from django.db import connection

# Register new apps in django_content_type table
cursor = connection.cursor()
try:
    cursor.execute(\"\"\"
    INSERT INTO django_content_type (app_label, model)
    VALUES ('patients', 'patient'), ('patients', 'patientaccount'), 
           ('patients', 'medicalrecord'), ('patients', 'patientdocument'),
           ('hospitals', 'hospital'), ('hospitals', 'department')
    ON CONFLICT DO NOTHING;
    \"\"\")
    print('New app models registered in django_content_type')
except Exception as e:
    print(f'Error registering new apps: {e}')
finally:
    cursor.close()
"

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Build completed successfully."