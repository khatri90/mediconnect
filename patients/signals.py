import random
import string
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.contrib.auth.hashers import make_password
from .models import Patient, PatientAccount
import logging

logger = logging.getLogger(__name__)

def generate_random_password(length=10):
    """Generate a random password of specified length"""
    characters = string.ascii_letters + string.digits + "!@#$%^&*()"
    # Ensure at least one of each type of character
    password = random.choice(string.ascii_lowercase)
    password += random.choice(string.ascii_uppercase)
    password += random.choice(string.digits)
    password += random.choice("!@#$%^&*()")
    # Fill the rest randomly
    password += ''.join(random.choice(characters) for i in range(length-4))
    # Shuffle the password
    password_list = list(password)
    random.shuffle(password_list)
    return ''.join(password_list)

@receiver(post_save, sender=Patient)
def create_patient_account(sender, instance, created, **kwargs):
    """Create a PatientAccount instance when a new Patient is created"""
    if created:
        try:
            # Check if patient already has an account
            PatientAccount.objects.get(patient=instance)
            logger.info(f"Patient {instance.name} already has an account.")
        except PatientAccount.DoesNotExist:
            # Generate random password if needed
            if not hasattr(instance, '_password'):
                instance._password = generate_random_password()
            
            # Create account
            account = PatientAccount(
                patient=instance,
                username=instance.email,
                password_hash=make_password(instance._password)
            )
            account.save()
            
            logger.info(f"Created account for patient {instance.name}")