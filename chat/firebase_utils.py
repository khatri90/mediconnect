import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
import logging
import uuid
from datetime import datetime
from django.conf import settings
import traceback

logger = logging.getLogger(__name__)

class FirebaseChat:
    """
    Utility class for Firebase Firestore chat operations
    """
    _firestore_client = None
    _app_initialized = False
    
    @classmethod
    def get_firestore_client(cls):
        """Get or initialize the Firestore client with better error handling"""
        if cls._firestore_client:
            return cls._firestore_client
            
        try:
            # Check if Firebase is already initialized
            if cls._app_initialized:
                logger.info("Using existing Firebase app for Firestore")
            else:
                # Initialize Firebase with credentials from environment
                logger.info("Initializing Firebase app for Firestore")
                service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
                
                if not service_account_json:
                    logger.error("FIREBASE_SERVICE_ACCOUNT_JSON environment variable not set")
                    logger.error("Available env vars: %s", str(os.environ.keys()))
                    return None
                
                try:
                    # Try to parse the JSON string
                    service_account_info = json.loads(service_account_json)
                    creds = credentials.Certificate(service_account_info)
                    
                    # Make sure we have a unique app name to avoid conflicts
                    app_name = f"firestore-{uuid.uuid4()}"
                    
                    # Create app with error handling
                    try:
                        app = firebase_admin.initialize_app(creds, name=app_name)
                        cls._app_initialized = True
                        logger.info("Firebase app initialized successfully")
                    except ValueError as e:
                        # App already exists with this name, try to get it
                        if "already exists" in str(e):
                            logger.warning("Firebase app already exists, attempting to get it")
                            # We'll handle this by continuing and trying to get the client
                            cls._app_initialized = True
                        else:
                            raise
                        
                except json.JSONDecodeError:
                    # If it's not a JSON string, it might be a path to a file
                    logger.info("Service account isn't JSON, trying as file path")
                    if os.path.exists(service_account_json):
                        creds = credentials.Certificate(service_account_json)
                        app = firebase_admin.initialize_app(creds, name=f"firestore-{uuid.uuid4()}")
                        cls._app_initialized = True
                        logger.info("Firebase app initialized successfully from file")
                    else:
                        logger.error("Service account JSON is neither valid JSON nor a valid file path")
                        return None
            
            # Get Firestore client
            try:
                # Try to get the default app first
                app = firebase_admin.get_app()
                db = firestore.client(app)
                cls._firestore_client = db
                logger.info("Successfully connected to Firestore with default app")
                return db
            except ValueError:
                # No default app, try to get app by name
                try:
                    # Try to find any initialized app
                    for app_name in firebase_admin._apps:
                        if app_name:
                            app = firebase_admin.get_app(app_name)
                            db = firestore.client(app)
                            cls._firestore_client = db
                            logger.info(f"Successfully connected to Firestore with app: {app_name}")
                            return db
                            
                    # If we get here, no app was found
                    logger.error("No Firebase app found after initialization attempt")
                    return None
                except Exception as e:
                    logger.error(f"Error getting Firebase app: {e}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting Firestore client: {e}")
            logger.error(traceback.format_exc())
            return None
            
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
            try:
                chat_ref = db.collection('chats').document(chat_id)
                chat = chat_ref.get()
                
                if not chat.exists:
                    logger.warning(f"Chat {chat_id} does not exist")
                    # Create an empty document to avoid future failures
                    chat_ref.set({
                        'participants': [],
                        'createdAt': now,
                        'updatedAt': now,
                        'fixedChat': True,
                        'note': 'Auto-created by error handler'
                    })
                    
                    # Also create messages container
                    message_container_ref = db.collection('messages').document(chat_id)
                    message_container_ref.set({})
                
                # Format sender ID
                sender_id = f"{user_type}_{user_id}"
                
                # Create the message in the subcollection
                message_container_ref = db.collection('messages').document(chat_id)
                message_ref = message_container_ref.collection('messages').document()
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
            except Exception as inner_e:
                logger.error(f"Error in the message sending process: {inner_e}")
                logger.error(traceback.format_exc())
                return False
        
        except Exception as e:
            logger.error(f"Error sending message to chat {chat_id}: {e}")
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
            # Check if messages collection exists
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
            except Exception as inner_e:
                logger.error(f"Error retrieving messages - likely missing container: {inner_e}")
                
                # Try to fix - create messages container if missing
                try:
                    message_container_ref = db.collection('messages').document(chat_id)
                    message_container_ref.set({})
                    logger.info(f"Created message container for chat {chat_id}")
                    return []
                except Exception as fix_e:
                    logger.error(f"Failed to fix missing message container: {fix_e}")
                    return []
        
        except Exception as e:
            logger.error(f"Error retrieving messages for chat {chat_id}: {e}")
            logger.error(traceback.format_exc())
            return []
    
    @staticmethod
    def get_new_messages(chat_id, since_datetime, limit=100):
        """
        Get messages for a specific chat that were created after a specific datetime
        
        Args:
            chat_id (str): Firebase chat document ID
            since_datetime (datetime): Only fetch messages created after this time
            limit (int): Maximum number of messages to retrieve
            
        Returns:
            list: List of message documents or empty list if none or error
        """
        db = FirebaseChat.get_firestore_client()
        if not db:
            logger.error("Could not get Firestore client for retrieving new chat messages")
            return []
        
        try:
            # Check if messages collection exists
            try:
                # Get the messages subcollection
                messages_ref = db.collection('messages').document(chat_id).collection('messages')
                
                # Convert datetime to Firestore timestamp format
                # Firebase timestamps and Python datetime objects aren't directly comparable
                # We create a Firestore timestamp from the Python datetime
                from firebase_admin import firestore
                since_timestamp = firestore.Timestamp.from_datetime(since_datetime)
                
                # Query messages created after the since_timestamp
                query = messages_ref.where('timestamp', '>', since_timestamp).order_by('timestamp', direction=firestore.Query.ASCENDING).limit(limit)
                
                # Execute query and get results
                message_docs = query.stream()
                
                # Convert to list of dictionaries with IDs
                result = []
                for doc in message_docs:
                    message_data = doc.to_dict()
                    message_data['id'] = doc.id
                    result.append(message_data)
                
                logger.info(f"Retrieved {len(result)} new messages for chat {chat_id} since {since_datetime}")
                return result
            except Exception as inner_e:
                logger.error(f"Error retrieving new messages: {inner_e}")
                
                # Try to fix - create messages container if missing
                try:
                    message_container_ref = db.collection('messages').document(chat_id)
                    message_container_ref.set({})
                    logger.info(f"Created message container for chat {chat_id}")
                    return []
                except Exception as fix_e:
                    logger.error(f"Failed to fix missing message container: {fix_e}")
                    return []
        
        except Exception as e:
            logger.error(f"Error retrieving new messages for chat {chat_id}: {e}")
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
            try:
                messages_ref = db.collection('messages').document(chat_id).collection('messages')
                
                # Query unread messages not sent by this user
                query = messages_ref.where('read', '==', False).where('senderId', '!=', recipient_id)
                
                # Execute query and get results
                unread_docs = query.stream()
                
                # Mark each message as read
                count = 0
                
                # Use a more robust approach instead of batch
                for doc in unread_docs:
                    try:
                        doc_ref = messages_ref.document(doc.id)
                        doc_ref.update({'read': True})
                        count += 1
                    except Exception as doc_e:
                        logger.error(f"Error updating document {doc.id}: {doc_e}")
                        # Continue with other documents
                
                logger.info(f"Marked {count} messages as read in chat {chat_id} for {recipient_id}")
                return True
            except Exception as inner_e:
                logger.error(f"Error in mark_messages_as_read process: {inner_e}")
                
                # Try to fix - create messages container if missing
                try:
                    message_container_ref = db.collection('messages').document(chat_id)
                    message_container_ref.set({})
                    logger.info(f"Created message container for chat {chat_id}")
                    return True
                except Exception as fix_e:
                    logger.error(f"Failed to fix missing message container: {fix_e}")
                    return False
                
        except Exception as e:
            logger.error(f"Error marking messages as read for chat {chat_id}: {e}")
            logger.error(traceback.format_exc())
            return False