from django.apps import AppConfig


class DoctorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'doctors'
    def ready(self):
        """Import signal handlers when the app is ready"""
        import doctors.signals
