from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'patients'
    
    def ready(self):
        """Import signal handlers when the app is ready"""
        import patients.signals