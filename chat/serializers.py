from rest_framework import serializers
from .models import Chat
from doctors.models import Appointment, Doctor
from doctors.serializers import AppointmentSerializer
from django.contrib.auth import get_user_model

User = get_user_model()

class ChatSerializer(serializers.ModelSerializer):
    appointment = AppointmentSerializer(read_only=True)
    
    class Meta:
        model = Chat
        fields = ('id', 'appointment', 'firebase_chat_id', 'created_at', 'updated_at')
        read_only_fields = ('firebase_chat_id',)

class ChatListItemSerializer(serializers.ModelSerializer):
    doctor_name = serializers.SerializerMethodField()
    patient_name = serializers.CharField(source='appointment.patient_name')
    patient_id = serializers.IntegerField(source='appointment.patient_id')
    appointment_date = serializers.DateField(source='appointment.appointment_date')
    appointment_id = serializers.CharField(source='appointment.appointment_id')
    
    class Meta:
        model = Chat
        fields = ('id', 'firebase_chat_id', 'doctor_name', 'patient_name', 'patient_id', 
                  'appointment_date', 'appointment_id', 'updated_at')
    
    def get_doctor_name(self, obj):
        return obj.appointment.doctor.full_name

class MessageSerializer(serializers.Serializer):
    """Serializer for Firebase chat messages (not a Django model)"""
    id = serializers.CharField(required=False, read_only=True)
    text = serializers.CharField()
    senderId = serializers.CharField(required=False, read_only=True)
    senderType = serializers.CharField(required=False, read_only=True)
    timestamp = serializers.DateTimeField(required=False, read_only=True)
    read = serializers.BooleanField(required=False, read_only=True, default=False)

class SendMessageSerializer(serializers.Serializer):
    """Serializer for sending a new message"""
    chat_id = serializers.CharField()
    text = serializers.CharField()