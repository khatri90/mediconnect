# Create a custom migration file
# Save this as doctors/migrations/0006_alter_appointment_status_default.py

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('doctors', '0005_alter_appointment_appointment_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appointment',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending Confirmation'), ('confirmed', 'Confirmed'), ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('no_show', 'No Show')], default='confirmed', max_length=20),
        ),
    ]