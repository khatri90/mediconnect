# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('doctors', '0003_doctoravailabilitysettings_appointment_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='appointment_id',
            field=models.CharField(blank=True, help_text='Unique 6-character hexadecimal ID', max_length=6, null=True, unique=True),
        ),
    ]