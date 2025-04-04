# patients/migrations/manual_patient_structure.py

from django.db import migrations

class Migration(migrations.Migration):
    """
    This migration doesn't actually make changes but ensures Django knows
    about the tables created via raw SQL.
    """
    dependencies = [
        ('patients', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql='',  # Empty SQL since tables were created manually
            reverse_sql='',
            state_operations=[
                # Describe state changes here if needed
            ]
        ),
    ]