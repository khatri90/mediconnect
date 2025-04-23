from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from django.shortcuts import get_object_or_404
from django.db import transaction

from .models import Chat
from doctors.models import Appointment, Doctor
from .serializers import (
    ChatSerializer,
    ChatListItemSerializer,
    MessageSerializer,
    SendMessageSerializer
)
from .firebase_utils import FirebaseChat
import logging
import jwt
from django.conf import settings

logger = logging.getLogger(__name__)

# JWT settings - using doctor_id in doctomoris app
JWT_SECRET = getattr(settings, 'JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = 'HS256'

def get_user_from_token(request):
    """Extract user info from token"""
    auth_header = request.headers.get('Authorization')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return None, None
    
    token = auth_header.split(' ')[1]
    
    try:
        # First try as doctor token
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        doctor_id = payload.get('doctor_id')
        
        if doctor_id:
            return 'doctor', doctor_id
        
        # If not doctor, try as patient
        patient_id = payload.get('patient_id')
        if patient_id:
            return 'patient', patient_id
            
        return None, None
    
    except jwt.InvalidTokenError:
        return None, None

# Custom permission classes
class IsChatParticipant(permissions.BasePermission):
    """
    Custom permission to only allow participants of a chat to access it
    """
    def has_permission(self, request, view):
        # For list views, allow any authenticated user
        # The queryset will be filtered based on the user
        user_type, user_id = get_user_from_token(request)
        return user_type is not None and user_id is not None
    
    def has_object_permission(self, request, view, obj):
        # For detail views, check if user is participant
        user_type, user_id = get_user_from_token(request)
        
        if not user_type or not user_id:
            return False
        
        # Check if user is a participant
        appointment = obj.appointment
        if user_type == 'doctor':
            return appointment.doctor.id == int(user_id)
        elif user_type == 'patient':
            return appointment.patient_id == int(user_id)
        
        return False

class ChatListView(generics.ListAPIView):
    """List all chats for the current user"""
    serializer_class = ChatListItemSerializer
    permission_classes = [IsChatParticipant]
    
    def get_queryset(self):
        """Return all chats where the user is a participant"""
        user_type, user_id = get_user_from_token(self.request)
        
        if not user_type or not user_id:
            return Chat.objects.none()
        
        # Filter based on user type
        if user_type == 'doctor':
            try:
                doctor = Doctor.objects.get(id=user_id)
                return Chat.objects.filter(appointment__doctor=doctor)
            except Doctor.DoesNotExist:
                return Chat.objects.none()
        elif user_type == 'patient':
            return Chat.objects.filter(appointment__patient_id=user_id)
        
        return Chat.objects.none()

class ChatDetailView(generics.RetrieveAPIView):
    """Retrieve a specific chat by Firebase ID"""
    serializer_class = ChatSerializer
    permission_classes = [IsChatParticipant]
    lookup_field = 'firebase_chat_id'
    
    def get_queryset(self):
        return Chat.objects.all().select_related(
            'appointment', 'appointment__doctor'
        )

class ChatMessagesView(APIView):
    """View for getting messages from a Firebase chat"""
    permission_classes = [IsChatParticipant]
    
    def get(self, request, firebase_chat_id):
        # First, check if the chat exists
        chat = get_object_or_404(Chat, firebase_chat_id=firebase_chat_id)
        
        # Check if user has permission (redundant with IsChatParticipant, but kept for clarity)
        user_type, user_id = get_user_from_token(request)
        if not user_type or not user_id:
            return Response(
                {'detail': 'Invalid authentication token'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Get messages from Firebase
        messages = FirebaseChat.get_chat_messages(firebase_chat_id)
        
        # Serialize messages
        serializer = MessageSerializer(messages, many=True)
        
        # Mark messages as read (async)
        FirebaseChat.mark_messages_as_read(firebase_chat_id, user_id, user_type)
        
        return Response(serializer.data)

class SendMessageView(APIView):
    """View for sending a message to a Firebase chat"""
    permission_classes = [IsChatParticipant]
    
    def post(self, request):
        serializer = SendMessageSerializer(data=request.data)
        
        if serializer.is_valid():
            chat_id = serializer.validated_data['chat_id']
            text = serializer.validated_data['text']
            
            # Check if chat exists and user has permission
            chat = get_object_or_404(Chat, firebase_chat_id=chat_id)
            
            # Get user info from token
            user_type, user_id = get_user_from_token(request)
            if not user_type or not user_id:
                return Response(
                    {'detail': 'Invalid authentication token'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Verify the user is a participant
            appointment = chat.appointment
            if (user_type == 'doctor' and appointment.doctor.id != int(user_id)) or \
               (user_type == 'patient' and appointment.patient_id != int(user_id)):
                return Response(
                    {'detail': 'You do not have permission to send messages to this chat'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Send message to Firebase
            success = FirebaseChat.send_message(
                chat_id=chat_id,
                user_id=user_id,
                user_type=user_type,
                text=text
            )
            
            if success:
                return Response(
                    {'detail': 'Message sent successfully'},
                    status=status.HTTP_201_CREATED
                )
            else:
                return Response(
                    {'detail': 'Failed to send message'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class MarkMessagesReadView(APIView):
    """View for marking messages as read in a Firebase chat"""
    permission_classes = [IsChatParticipant]
    
    def post(self, request, firebase_chat_id):
        # Check if chat exists
        chat = get_object_or_404(Chat, firebase_chat_id=firebase_chat_id)
        
        # Get user info from token
        user_type, user_id = get_user_from_token(request)
        if not user_type or not user_id:
            return Response(
                {'detail': 'Invalid authentication token'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Mark messages as read
        success = FirebaseChat.mark_messages_as_read(
            chat_id=firebase_chat_id,
            user_id=user_id,
            user_type=user_type
        )
        
        if success:
            return Response(
                {'detail': 'Messages marked as read'},
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {'detail': 'Failed to mark messages as read'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CreateChatView(APIView):
    """View for creating a chat for an appointment"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        appointment_id = request.data.get('appointment_id')
        
        if not appointment_id:
            return Response(
                {'detail': 'Appointment ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Find the appointment
            appointment = Appointment.objects.get(appointment_id=appointment_id)
            
            # Check if a chat already exists for this appointment
            if hasattr(appointment, 'chat'):
                return Response(
                    {'detail': 'A chat already exists for this appointment',
                     'firebase_chat_id': appointment.chat.firebase_chat_id},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create a chat in Firebase
            firebase_chat_id = FirebaseChat.create_chat(
                doctor_id=appointment.doctor.id,
                patient_id=appointment.patient_id,
                appointment_id=appointment.appointment_id
            )
            
            if not firebase_chat_id:
                return Response(
                    {'detail': 'Failed to create chat in Firebase'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Create a Chat model instance
            chat = Chat.objects.create(
                appointment=appointment,
                firebase_chat_id=firebase_chat_id
            )
            
            return Response({
                'detail': 'Chat created successfully',
                'firebase_chat_id': firebase_chat_id,
                'chat_id': chat.id
            }, status=status.HTTP_201_CREATED)
            
        except Appointment.DoesNotExist:
            return Response(
                {'detail': 'Appointment not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error creating chat: {e}")
            return Response(
                {'detail': f'Error creating chat: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )