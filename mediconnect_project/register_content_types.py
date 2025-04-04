# register_content_types.py
# Run this script after your build process to ensure content types are properly registered

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
cursor.close()

print("Done! Content types and permissions have been properly registered.")