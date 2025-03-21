# doctors/signals.py

import random
import string
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.contrib.auth.hashers import make_password
from .models import Doctor, DoctorAccount
import logging
from django.core.mail import send_mail


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

@receiver(pre_save, sender=Doctor)
def doctor_status_changed(sender, instance, **kwargs):
    """Signal to handle doctor status changes"""
    try:
        # Check if this is a new record
        if instance.pk is None:
            return
        
        # Get the doctor's previous state
        try:
            previous_state = Doctor.objects.get(pk=instance.pk)
        except Doctor.DoesNotExist:
            return
        
        # Check if status changed from pending/rejected to approved
        if previous_state.status != 'approved' and instance.status == 'approved':
            logger.info(f"Doctor {instance.full_name} has been approved. Creating login account.")
            
            # Check if doctor already has an account
            try:
                DoctorAccount.objects.get(doctor=instance)
                logger.info(f"Doctor {instance.full_name} already has an account.")
                return
            except DoctorAccount.DoesNotExist:
                pass
            
            # Generate random password
            password = generate_random_password()
            
            # Create account with error handling
            try:
                account = DoctorAccount(
                    doctor=instance,
                    username=instance.email,  # Use email as username
                    password_hash=make_password(password)  # Directly set hashed password
                )
                account.save()
                
                # Store the password temporarily so we can access it in the admin
                instance._generated_password = password
                
                # Send email - wrapped in try/except
                try:
                    subject = "MediConnect - Your Account has been Approved"
                    message = f"""Hello {instance.full_name},

Your MediConnect account has been approved! You can now log in to access your dashboard.

Login Details:
- Email: {instance.email}
- Password: {password}

For security reasons, we recommend changing your password after your first login.

If you have any questions, please contact our support team.

Best regards,
The MediConnect Team
"""
                    from_email = "noreply@mediconnect.com"
                    recipient_list = [instance.email]
                    
                    send_mail(
                        subject,
                        message,
                        from_email,
                        recipient_list,
                        fail_silently=True,  # Changed to fail_silently=True
                    )
                    
                    logger.info(f"Credentials email sent to {instance.email}")
                except Exception as e:
                    logger.error(f"Failed to send email: {str(e)}")
            
            except Exception as e:
                logger.error(f"Failed to create account: {str(e)}")
                
    except Exception as e:
        # Catch any exceptions to prevent signal from breaking admin
        logger.error(f"Error in doctor_status_changed signal: {str(e)}")
