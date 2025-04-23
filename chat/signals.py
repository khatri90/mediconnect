from django.db.models.signals import post_save
from django.dispatch import receiver
from doctors.models import Appointment
from .models import Chat
from .firebase_utils import FirebaseChat
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Appointment)
def create_chat_for_appointment(sender, instance, created, **kwargs):
    """Create a chat when a new appointment is created"""
    
    if created:  # Only run when appointment is first created
        try:
            # Check if chat already exists
            if hasattr(instance, 'chat') and instance.chat:
                logger.info(f"Chat already exists for appointment {instance.appointment_id}")
                return
                
            # Create a chat in Firebase
            firebase_chat_id = FirebaseChat.create_chat(
                doctor_id=instance.doctor.id,
                patient_id=instance.patient_id,
                appointment_id=instance.appointment_id
            )
            
            if firebase_chat_id:
                # Create Chat model instance
                Chat.objects.create(
                    appointment=instance,
                    firebase_chat_id=firebase_chat_id
                )
                logger.info(f"Created chat {firebase_chat_id} for appointment {instance.appointment_id}")
            else:
                logger.error(f"Failed to create Firebase chat for appointment {instance.appointment_id}")
                
        except Exception as e:
            logger.error(f"Error in create_chat_for_appointment signal handler: {e}")