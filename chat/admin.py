from django.contrib import admin
from .models import Chat

@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ('id', 'appointment_display', 'firebase_chat_id', 'created_at', 'updated_at')
    search_fields = ('appointment__doctor__first_name', 'appointment__doctor__last_name', 
                     'appointment__patient_name', 'appointment__appointment_id', 'firebase_chat_id')
    readonly_fields = ('firebase_chat_id', 'created_at', 'updated_at')
    
    def appointment_display(self, obj):
        """Display appointment ID in a more readable format"""
        return f"{obj.appointment.appointment_id}: {obj.appointment.doctor.full_name} with {obj.appointment.patient_name}"
    appointment_display.short_description = "Appointment"