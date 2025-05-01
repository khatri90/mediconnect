from rest_framework import generics, status, permissions 
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import datetime

from .models import Chat
from doctors.models import Appointment, Doctor
from .serializers import (
    ChatSerializer,
    ChatListItemSerializer,
    MessageSerializer,
    SendMessageSerializer
)
from .firebase_utils import FirebaseChat
# Import the new timestamp utilities
from .timestamp_utils import parse_timestamp, format_timestamp, now
import logging
import jwt
from django.conf import settings
import traceback
import dateutil.parser  # Make sure you have python-dateutil installed

logger = logging.getLogger(__name__)

# JWT settings
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
        
        # Get base queryset based on user type
        if user_type == 'doctor':
            try:
                doctor = Doctor.objects.get(id=user_id)
                queryset = Chat.objects.filter(appointment__doctor=doctor)
            except Doctor.DoesNotExist:
                return Chat.objects.none()
        elif user_type == 'patient':
            queryset = Chat.objects.filter(appointment__patient_id=user_id)
        else:
            return Chat.objects.none()
        
        # Apply timestamp filter for incremental updates if provided
        since_timestamp = self.request.query_params.get('since', None)
        if since_timestamp:
            try:
                # Convert ISO 8601 string to datetime object
                import dateutil.parser
                since_datetime = dateutil.parser.parse(since_timestamp)
                
                # Filter to get only chats updated since the provided timestamp
                queryset = queryset.filter(updated_at__gt=since_datetime)
                
                logger.info(f"Filtered chats for {user_type}_{user_id} since {since_timestamp}: {queryset.count()} results")
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid timestamp format: {since_timestamp}, error: {e}")
                # If timestamp is invalid, don't apply the filter
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        """Override list method to include current timestamp in response"""
        response = super().list(request, *args, **kwargs)
        
        # Add current timestamp for next incremental update
        response.data = {
            'status': 'success',
            'chats': response.data,
            'timestamp': datetime.now().isoformat()
        }
        
        return response
    
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
        try:
            # First, check if the chat exists
            chat = get_object_or_404(Chat, firebase_chat_id=firebase_chat_id)
            
            # Check if user has permission (redundant with IsChatParticipant, but kept for clarity)
            user_type, user_id = get_user_from_token(request)
            if not user_type or not user_id:
                return Response(
                    {'detail': 'Invalid authentication token'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Check for 'since' parameter for incremental updates
            since_timestamp = request.query_params.get('since', None)
            
            # Get messages from Firebase
            if since_timestamp:
                logger.info(f"Fetching messages for chat {firebase_chat_id} since {since_timestamp}")
                try:
                    # Convert ISO 8601 string to datetime object
                    import dateutil.parser
                    since_datetime = dateutil.parser.parse(since_timestamp)
                    
                    # Get new messages from Firebase
                    messages = FirebaseChat.get_new_messages(firebase_chat_id, since_datetime)
                except (ValueError, TypeError) as e:
                    logger.error(f"Invalid timestamp format: {since_timestamp}, error: {e}")
                    # Fall back to getting all messages
                    messages = FirebaseChat.get_chat_messages(firebase_chat_id)
            else:
                # No timestamp provided, get all messages
                messages = FirebaseChat.get_chat_messages(firebase_chat_id)
            
            # Serialize messages
            serializer = MessageSerializer(messages, many=True)
            
            # Mark messages as read (async)
            try:
                FirebaseChat.mark_messages_as_read(firebase_chat_id, user_id, user_type)
            except Exception as e:
                # Log but don't fail if marking as read fails
                logger.error(f"Error marking messages as read: {e}")
                logger.error(traceback.format_exc())
            
            return Response({
                'status': 'success',
                'messages': serializer.data,
                'timestamp': datetime.now().isoformat()  # Include current timestamp for next incremental update
            })
        except Exception as e:
            logger.error(f"Error in ChatMessagesView: {e}")
            logger.error(traceback.format_exc())
            # Return empty list rather than error
            return Response({
                'status': 'error',
                'messages': [],
                'error': str(e)
            })
            
class SendMessageView(APIView):
    """View for sending a message to a Firebase chat"""
    permission_classes = [IsChatParticipant]
    
    def post(self, request):
        try:
            serializer = SendMessageSerializer(data=request.data)
            
            if serializer.is_valid():
                chat_id = serializer.validated_data['chat_id']
                text = serializer.validated_data['text']
                
                # Check if chat exists and user has permission
                try:
                    chat = Chat.objects.get(firebase_chat_id=chat_id)
                except Chat.DoesNotExist:
                    # Try finding by id instead
                    try:
                        chat = Chat.objects.get(id=chat_id)
                        chat_id = chat.firebase_chat_id  # Use the firebase_chat_id
                    except (Chat.DoesNotExist, ValueError):
                        logger.error(f"Chat not found with ID: {chat_id}")
                        return Response(
                            {'detail': 'Chat not found'},
                            status=status.HTTP_404_NOT_FOUND
                        )
                
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
                try:
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
                        logger.error(f"Failed to send message to Firebase for chat: {chat_id}")
                        return Response(
                            {'detail': 'Failed to send message'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
                except Exception as e:
                    logger.error(f"Exception sending message to Firebase: {e}")
                    logger.error(traceback.format_exc())
                    return Response(
                        {'detail': 'Failed to send message'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in SendMessageView: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {'detail': 'An unexpected error occurred'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class MarkMessagesReadView(APIView):
    """View for marking messages as read in a Firebase chat"""
    permission_classes = [IsChatParticipant]
    
    def post(self, request, firebase_chat_id):
        try:
            # Check if chat exists
            try:
                chat = Chat.objects.get(firebase_chat_id=firebase_chat_id)
            except Chat.DoesNotExist:
                logger.error(f"Chat not found with firebase_chat_id: {firebase_chat_id}")
                return Response(
                    {'detail': 'Chat not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get user info from token
            user_type, user_id = get_user_from_token(request)
            if not user_type or not user_id:
                return Response(
                    {'detail': 'Invalid authentication token'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Mark messages as read
            try:
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
                    logger.error(f"Failed to mark messages as read in Firebase for chat: {firebase_chat_id}")
                    # Return success anyway to avoid client errors
                    return Response(
                        {'detail': 'Messages marked as read'},
                        status=status.HTTP_200_OK
                    )
            except Exception as e:
                logger.error(f"Exception marking messages as read in Firebase: {e}")
                logger.error(traceback.format_exc())
                # Return success anyway to avoid client errors
                return Response(
                    {'detail': 'Messages marked as read'},
                    status=status.HTTP_200_OK
                )
                
        except Exception as e:
            logger.error(f"Unexpected error in MarkMessagesReadView: {e}")
            logger.error(traceback.format_exc())
            # Return success anyway to avoid client errors
            return Response(
                {'detail': 'Messages marked as read'},
                status=status.HTTP_200_OK
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
            try:
                appointment = Appointment.objects.get(appointment_id=appointment_id)
            except Appointment.DoesNotExist:
                # Try with numeric ID
                try:
                    appointment = Appointment.objects.get(id=int(appointment_id))
                except (Appointment.DoesNotExist, ValueError):
                    return Response(
                        {'detail': 'Appointment not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
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
            
        except Exception as e:
            logger.error(f"Error creating chat: {e}")
            logger.error(traceback.format_exc())
            return Response(
                {'detail': f'Error creating chat: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class RegisterDeviceTokenView(APIView):
    """View for registering a device token for push notifications"""
    
    def post(self, request):
        """Register a device FCM token for the current user"""
        try:
            # Extract user info from token (using your existing function)
            user_type, user_id = get_user_from_token(request)
            
            if not user_type or not user_id:
                return Response(
                    {'detail': 'Invalid authentication token'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Only allow patients to register tokens
            if user_type != 'patient':
                return Response(
                    {'detail': 'Only patients can register for notifications'},
                    status=status.HTTP_403_FORBIDDEN
                )
                
            # Get the token from the request data
            token = request.data.get('token')
            device_type = request.data.get('device_type', 'android')
            
            if not token:
                return Response(
                    {'detail': 'FCM token is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Save or update the token
            device_token, created = DeviceToken.objects.update_or_create(
                patient_id=user_id,
                token=token,
                defaults={
                    'device_type': device_type,
                    'active': True
                }
            )
            
            return Response(
                {'detail': 'Device token registered successfully'},
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error registering device token: {e}")
            return Response(
                {'detail': 'Failed to register device token'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
class UnregisterDeviceTokenView(APIView):
    """View for unregistering a device token"""
    
    def post(self, request):
        """Unregister a device FCM token"""
        try:
            # Extract user info from token
            user_type, user_id = get_user_from_token(request)
            
            if not user_type or not user_id:
                return Response(
                    {'detail': 'Invalid authentication token'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Get the token from the request data
            token = request.data.get('token')
            
            if not token:
                return Response(
                    {'detail': 'FCM token is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Mark the token as inactive
            updated = DeviceToken.objects.filter(
                patient_id=user_id,
                token=token
            ).update(active=False)
            
            if updated:
                return Response(
                    {'detail': 'Device token unregistered successfully'},
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'detail': 'Token not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
        except Exception as e:
            logger.error(f"Error unregistering device token: {e}")
            return Response(
                {'detail': 'Failed to unregister device token'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )