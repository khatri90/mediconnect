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
        
        # Now that all records have been populated, make the column non-nullable for new records
        cursor.execute(\"\"\"
        ALTER TABLE doctors_appointment 
        ALTER COLUMN appointment_id SET NOT NULL;
        \"\"\")
        print('Modified appointment_id to NOT NULL')
        
    except Exception as e:
        print(f'Error working with appointment_id column: {e}')
else:
    print('Column appointment_id already exists')

cursor.close()
conn.close()
"

# Ensure appointment_id is shown in admin by creating a small patch
echo "Ensuring appointment_id is visible in admin..."
cat > admin_fix.py << EOL
import django
import os

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediconnect_project.settings')

# Initialize Django
django.setup()

from django.contrib import admin
from doctors.models import Appointment
from doctors.admin import AppointmentAdmin

# Check if current list_display includes appointment_id
has_appt_id = False
for admin_instance in admin.site._registry.values():
    if isinstance(admin_instance, AppointmentAdmin):
        if 'appointment_id' in admin_instance.list_display:
            has_appt_id = True
            print("Admin already has appointment_id in list_display")
        else:
            # Add appointment_id to list_display
            admin_instance.list_display = ['appointment_id'] + list(admin_instance.list_display)
            print("Added appointment_id to list_display")
            
            # Make sure fieldsets include appointment_id
            for name, options in admin_instance.fieldsets:
                if name == 'Appointment Information' and 'appointment_id' not in options['fields']:
                    if isinstance(options['fields'], list):
                        options['fields'].insert(0, 'appointment_id')
                    elif isinstance(options['fields'], tuple):
                        options['fields'] = ('appointment_id',) + options['fields']
                    print("Added appointment_id to fieldsets")
                    break

if not has_appt_id:
    print("Warning: Could not find AppointmentAdmin instance to modify")
EOL

python admin_fix.py