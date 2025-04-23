from django.db import models
from doctors.models import Appointment, Doctor

class Chat(models.Model):
    """Model to link appointments with Firebase chat rooms"""
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='chat'
    )
    firebase_chat_id = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Chat for appointment {self.appointment.appointment_id}"
    
    class Meta:
        verbose_name = 'Chat'
        verbose_name_plural = 'Chats'