# doctors/migrations/0009_add_zoom_fields.py
# Note: This migration initially had syntax errors (zoom_meeting_id = instead of field=)
# It was manually fixed and fields were added directly to the database via SQL commands
# This corrected version ensures future migrations build on the proper schema

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('doctors', '0008_faq_supportticket'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='zoom_meeting_id',
            field=models.CharField(max_length=100, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='appointment',
            name='zoom_meeting_url',
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='appointment',
            name='zoom_meeting_password',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='appointment',
            name='zoom_meeting_status',
            field=models.CharField(blank=True, choices=[('scheduled', 'Scheduled'), ('started', 'Started'), ('completed', 'Completed'), ('missed', 'Missed'), ('failed', 'Failed')], default='scheduled', max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='appointment',
            name='zoom_host_joined',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='appointment',
            name='zoom_client_joined',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='appointment',
            name='zoom_meeting_duration',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]