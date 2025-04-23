import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
import logging
import uuid
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)

class FirebaseChat:
    """
    Utility class for Firebase Firestore chat operations
    """
    @staticmethod
    def get_firestore_client():
        """Get or initialize the Firestore client"""
        try:
            # Check if Firebase is already initialized
            app = firebase_admin.get_app()
            logger.info("Using existing Firebase app for Firestore")
        except ValueError:
            # Initialize Firebase with credentials from environment
            logger.info("Initializing Firebase app for Firestore")
            service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
            
            if not service_account_json:
                logger.error("FIREBASE_SERVICE_ACCOUNT_JSON environment variable not set")
                return None
            
            try:
                service_account_info = json.loads(service_account_json)
                creds = credentials.Certificate(service_account_info)
                app = firebase_admin.initialize_app(creds, name='firestore')
                logger.info("Firebase app initialized for Firestore")
            except Exception as e:
                logger.error(f"Error initializing Firebase app: {e}")
                return None
        
        # Get Firestore client
        try:
            db = firestore.client(app)
            return db
        except Exception as e:
            logger.error(f"Error getting Firestore client: {e}")
            return None
    
    @staticmethod
    def create_chat(doctor_id, patient_id, appointment_id):
        """
        Create a new chat in Firebase Firestore
        
        Args:
            doctor_id (int): Doctor's Django user ID
            patient_id (int): Patient's Django user ID
            appointment_id (str): Django appointment ID
            
        Returns:
            str: Firebase chat document ID or None if failed
        """
        db = FirebaseChat.get_firestore_client()
        if not db:
            logger.error("Could not get Firestore client for creating chat")
            return None
        
        try:
            # Generate a chat ID
            chat_id = str(uuid.uuid4())
            
            # Current timestamp
            now = datetime.now()
            
            # Create the chat document in the 'chats' collection
            chat_ref = db.collection('chats').document(chat_id)
            chat_data = {
                'participants': [f"doctor_{doctor_id}", f"patient_{patient_id}"],
                'appointmentId': str(appointment_id),
                'createdAt': now,
                'updatedAt': now,
                'lastMessage': {
                    'text': "Chat started",
                    'timestamp': now,
                    'senderId': 'system'
                }
            }
            chat_ref.set(chat_data)
            logger.info(f"Created chat document with ID: {chat_id}")
            
            # Create the message container document in the 'messages' collection
            message_container_ref = db.collection('messages').document(chat_id)
            message_container_ref.set({})
            logger.info(f"Created message container document with ID: {chat_id}")
            
            # Create a first system message in the subcollection
            message_ref = message_container_ref.collection('messages').document()
            message_data = {
                'text': "Welcome to your appointment chat. You can use this to communicate before and after your appointment.",
                'senderId': 'system',
                'senderType': 'system',
                'timestamp': now,
                'read': False
            }
            message_ref.set(message_data)
            logger.info(f"Created first message in chat {chat_id}")
            
            return chat_id
        
        except Exception as e:
            logger.error(f"Error creating chat in Firestore: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    @staticmethod
    def send_message(chat_id, user_id, user_type, text):
        """
        Send a message to a chat
        
        Args:
            chat_id (str): Firebase chat document ID
            user_id (int): Django user ID of sender
            user_type (str): 'doctor' or 'patient'
            text (str): Message text
            
        Returns:
            bool: Success status
        """
        db = FirebaseChat.get_firestore_client()
        if not db:
            logger.error("Could not get Firestore client for sending message")
            return False
        
        try:
            # Current timestamp
            now = datetime.now()
            
            # First, check if the chat exists and the user is a participant
            chat_ref = db.collection('chats').document(chat_id)
            chat = chat_ref.get()
            
            if not chat.exists:
                logger.error(f"Chat {chat_id} does not exist")
                return False
            
            # Format sender ID
            sender_id = f"{user_type}_{user_id}"
            
            # Verify sender is a participant (security check)
            chat_data = chat.to_dict()
            if sender_id not in chat_data.get('participants', []):
                logger.error(f"User {sender_id} is not a participant in chat {chat_id}")
                return False
            
            # Create the message in the subcollection
            message_ref = db.collection('messages').document(chat_id).collection('messages').document()
            message_data = {
                'text': text,
                'senderId': sender_id,
                'senderType': user_type,
                'timestamp': now,
                'read': False
            }
            message_ref.set(message_data)
            logger.info(f"Added message to chat {chat_id} from {sender_id}")
            
            # Update the lastMessage in the chat document
            chat_ref.update({
                'lastMessage': {
                    'text': text,
                    'timestamp': now,
                    'senderId': sender_id
                },
                'updatedAt': now
            })
            logger.info(f"Updated lastMessage for chat {chat_id}")
            
            return True
        
        except Exception as e:
            logger.error(f"Error sending message to chat {chat_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    @staticmethod
    def get_user_chats(user_id, user_type):
        """
        Get all chats for a specific user
        
        Args:
            user_id (int): Django user ID
            user_type (str): 'doctor' or 'patient'
            
        Returns:
            list: List of chat documents or empty list if none or error
        """
        db = FirebaseChat.get_firestore_client()
        if not db:
            logger.error("Could not get Firestore client for retrieving user chats")
            return []
        
        try:
            # Format participant ID
            participant_id = f"{user_type}_{user_id}"
            
            # Query chats where this user is a participant
            chats_ref = db.collection('chats')
            query = chats_ref.where('participants', 'array_contains', participant_id)
            
            # Execute query and get results
            chat_docs = query.stream()
            
            # Convert to list of dictionaries with IDs
            result = []
            for doc in chat_docs:
                chat_data = doc.to_dict()
                chat_data['id'] = doc.id
                result.append(chat_data)
            
            logger.info(f"Retrieved {len(result)} chats for user {participant_id}")
            return result
        
        except Exception as e:
            logger.error(f"Error retrieving chats for user {user_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    @staticmethod
    def get_chat_messages(chat_id, limit=50):
        """
        Get messages for a specific chat
        
        Args:
            chat_id (str): Firebase chat document ID
            limit (int): Maximum number of messages to retrieve
            
        Returns:
            list: List of message documents or empty list if none or error
        """
        db = FirebaseChat.get_firestore_client()
        if not db:
            logger.error("Could not get Firestore client for retrieving chat messages")
            return []
        
        try:
            # Get the messages subcollection
            messages_ref = db.collection('messages').document(chat_id).collection('messages')
            
            # Query messages ordered by timestamp
            query = messages_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
            
            # Execute query and get results
            message_docs = query.stream()
            
            # Convert to list of dictionaries with IDs
            result = []
            for doc in message_docs:
                message_data = doc.to_dict()
                message_data['id'] = doc.id
                result.append(message_data)
            
            # Reverse to get chronological order
            result.reverse()
            
            logger.info(f"Retrieved {len(result)} messages for chat {chat_id}")
            return result
        
        except Exception as e:
            logger.error(f"Error retrieving messages for chat {chat_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    @staticmethod
    def mark_messages_as_read(chat_id, user_id, user_type):
        """
        Mark all messages in a chat as read for a user
        
        Args:
            chat_id (str): Firebase chat document ID
            user_id (int): Django user ID
            user_type (str): 'doctor' or 'patient'
            
        Returns:
            bool: Success status
        """
        db = FirebaseChat.get_firestore_client()
        if not db:
            logger.error("Could not get Firestore client for marking messages as read")
            return False
        
        try:
            # Format recipient ID (we're marking messages from the other user as read)
            recipient_id = f"{user_type}_{user_id}"
            
            # Get the messages subcollection
            messages_ref = db.collection('messages').document(chat_id).collection('messages')
            
            # Query unread messages not sent by this user
            query = messages_ref.where('read', '==', False).where('senderId', '!=', recipient_id)
            
            # Execute query and get results
            unread_docs = query.stream()
            
            # Mark each message as read
            batch = db.batch()
            count = 0
            
            for doc in unread_docs:
                doc_ref = messages_ref.document(doc.id)
                batch.update(doc_ref, {'read': True})
                count += 1
            
            # Commit the batch if there are messages to update
            if count > 0:
                batch.commit()
                logger.info(f"Marked {count} messages as read in chat {chat_id} for {recipient_id}")
            
            return True
        
        except Exception as e:
            logger.error(f"Error marking messages as read for chat {chat_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False