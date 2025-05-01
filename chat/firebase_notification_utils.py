import os
import json
import firebase_admin
from firebase_admin import credentials, messaging
import logging
import traceback
from django.conf import settings
from .models import DeviceToken, Chat
from doctors.models import Appointment

logger = logging.getLogger(__name__)

class FirebaseNotification:
    """
    Utility class for Firebase Cloud Messaging (FCM) operations
    """
    _fcm_app_initialized = False
    
    @classmethod
    def initialize_fcm(cls):
        """Initialize Firebase Admin SDK for FCM if not already initialized"""
        if cls._fcm_app_initialized:
            return True
            
        try:
            # Get service account credentials from environment variable
            service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
            if not service_account_json:
                logger.error("FIREBASE_SERVICE_ACCOUNT_JSON environment variable not set")
                return False
            
            # Parse the JSON string to a Python dictionary
            try:
                service_account_info = json.loads(service_account_json)
                logger.info("Successfully parsed FIREBASE_SERVICE_ACCOUNT_JSON for FCM")
                
                # Check if Firebase is already initialized
                try:
                    app = firebase_admin.get_app()
                    logger.info("Firebase app already initialized for FCM, reusing existing app")
                    cls._fcm_app_initialized = True
                    return True
                except ValueError:
                    # App doesn't exist yet, initialize it
                    logger.info("Initializing new Firebase app for FCM")
                    creds = credentials.Certificate(service_account_info)
                    firebase_admin.initialize_app(creds)
                    cls._fcm_app_initialized = True
                    return True
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing FCM: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    @staticmethod
    def send_chat_notification(chat_id, sender_type, sender_id, message_text):
        """
        Send push notification to the recipient of a chat message
        
        Args:
            chat_id (str): Firebase chat document ID
            sender_type (str): 'doctor' or 'patient'
            sender_id (int/str): Django user ID of sender
            message_text (str): Message text to include in notification
            
        Returns:
            bool: Success status
        """
        try:
            if not FirebaseNotification.initialize_fcm():
                logger.error("Failed to initialize Firebase for FCM")
                return False
            
            # Determine recipient type and ID
            recipient_type = 'patient' if sender_type == 'doctor' else 'doctor'
            
            # For doctor->patient messages, we need to notify the patient
            if sender_type == 'doctor' and recipient_type == 'patient':
                try:
                    # Get the chat object to find the appointment
                    chat = Chat.objects.get(firebase_chat_id=chat_id)
                    appointment = chat.appointment
                    recipient_id = appointment.patient_id
                    doctor_name = appointment.doctor.full_name
                    
                    # Get active device tokens for this patient
                    device_tokens = DeviceToken.objects.filter(
                        patient_id=recipient_id,
                        active=True
                    ).values_list('token', flat=True)
                    
                    if not device_tokens:
                        logger.info(f"No active device tokens found for patient {recipient_id}")
                        return False
                    
                    # Create the notification message
                    notification = messaging.Notification(
                        title=f"New message from Dr. {doctor_name}",
                        body=message_text[:100]  # Truncate long messages
                    )
                    
                    # Data payload for the app to use
                    data = {
                        'chat_id': chat_id,
                        'appointment_id': appointment.appointment_id,
                        'sender_type': sender_type,
                        'sender_id': str(sender_id),
                        'notification_type': 'chat_message'
                    }
                    
                    # Send to each token
                    success_count = 0
                    invalid_tokens = []
                    
                    for token in device_tokens:
                        try:
                            message = messaging.Message(
                                notification=notification,
                                data=data,
                                token=token,
                                android=messaging.AndroidConfig(
                                    priority='high',
                                    notification=messaging.AndroidNotification(
                                        sound='default',
                                        click_action='FLUTTER_NOTIFICATION_CLICK'
                                    )
                                ),
                                apns=messaging.APNSConfig(
                                    payload=messaging.APNSPayload(
                                        aps=messaging.Aps(
                                            sound='default', 
                                            badge=1
                                        )
                                    )
                                )
                            )
                            
                            response = messaging.send(message)
                            logger.info(f"Successfully sent notification to token {token[:10]}...: {response}")
                            success_count += 1
                            
                        except firebase_admin.exceptions.FirebaseError as e:
                            logger.error(f"Error sending FCM to token {token[:10]}...: {str(e)}")
                            
                            # Check for invalid token
                            if 'invalid-argument' in str(e) or 'registration-token-not-registered' in str(e):
                                invalid_tokens.append(token)
                    
                    # Clean up invalid tokens
                    if invalid_tokens:
                        DeviceToken.objects.filter(token__in=invalid_tokens).update(active=False)
                        logger.info(f"Marked {len(invalid_tokens)} tokens as inactive")
                    
                    return success_count > 0
                    
                except Chat.DoesNotExist:
                    logger.error(f"Chat not found with ID {chat_id}")
                    return False
                except Exception as e:
                    logger.error(f"Error finding recipient for notification: {str(e)}")
                    logger.error(traceback.format_exc())
                    return False
            else:
                # We're not handling patient->doctor messages for now
                logger.info(f"Skipping notification for {sender_type}->{recipient_type} message")
                return False
                
        except Exception as e:
            logger.error(f"Error sending chat notification: {str(e)}")
            logger.error(traceback.format_exc())
            return False