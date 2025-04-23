#!/usr/bin/env python3
"""
Test script for Firebase chat functionality with a custom database name
"""

import os
import json
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    logger.error("Firebase admin SDK not installed. Run: pip install firebase-admin")
    sys.exit(1)

def initialize_firebase(service_account_path, database_id):
    """Initialize Firebase with a service account file and specific database ID"""
    try:
        # Try to get an existing app
        app = firebase_admin.get_app()
        logger.info("Using existing Firebase app")
    except ValueError:
        # Initialize with the provided service account file
        logger.info(f"Initializing Firebase with service account: {service_account_path}")
        logger.info(f"Using database ID: {database_id}")
        try:
            creds = credentials.Certificate(service_account_path)
            options = {
                'databaseId': database_id
            }
            app = firebase_admin.initialize_app(creds, options=options)
            logger.info("Firebase app initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Firebase app: {e}")
            return None
    
    # Get Firestore client
    try:
        db = firestore.client()
        logger.info("Successfully connected to Firestore")
        return db
    except Exception as e:
        logger.error(f"Error connecting to Firestore: {e}")
        return None

def list_collections(db):
    """List all collections in the database"""
    try:
        collections = db.collections()
        logger.info("Existing collections:")
        count = 0
        for collection in collections:
            count += 1
            logger.info(f"- {collection.id}")
        
        if count == 0:
            logger.info("No collections found in the database")
        
        return True
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        return False

def list_documents_in_collection(db, collection_name):
    """List all documents in a collection"""
    try:
        docs = db.collection(collection_name).stream()
        logger.info(f"Documents in '{collection_name}' collection:")
        doc_count = 0
        for doc in docs:
            doc_count += 1
            logger.info(f"- {doc.id}")
            logger.info(f"  Data: {doc.to_dict()}")
        
        if doc_count == 0:
            logger.info(f"No documents found in '{collection_name}' collection")
        
        return True
    except Exception as e:
        logger.error(f"Error listing documents in '{collection_name}': {e}")
        return False

def create_test_chat(db, doctor_id, patient_id, appointment_id):
    """Create a test chat in Firestore"""
    try:
        # Generate a chat ID
        import uuid
        chat_id = str(uuid.uuid4())
        logger.info(f"Generated chat ID: {chat_id}")
        
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

def main():
    """Test the Firebase connection by reading from the database"""
    logger.info("=== Firebase Connection Test (Custom Database) ===")
    
    # Get the service account file path
    service_account_path = input("Enter the path to the Firebase service account JSON file: ")
    if not os.path.exists(service_account_path):
        logger.error(f"File not found: {service_account_path}")
        return
    
    # Get the database ID
    database_id = input("Enter the Firestore database ID (e.g., 'doctomoris', leave empty for default): ")
    if not database_id:
        database_id = "(default)"
    
    # Initialize Firebase
    db = initialize_firebase(service_account_path, database_id)
    if not db:
        logger.error("Failed to initialize Firebase")
        return
    
    # List all collections
    logger.info("\nTesting collection access...")
    if not list_collections(db):
        return
    
    # Ask if user wants to create a test chat
    create_test = input("\nDo you want to create a test chat? (y/n): ").lower()
    if create_test == 'y':
        doctor_id = input("Enter doctor ID: ")
        patient_id = input("Enter patient ID: ")
        appointment_id = input("Enter appointment ID (or leave empty for 'TEST123'): ")
        if not appointment_id:
            appointment_id = "TEST123"
        
        chat_id = create_test_chat(db, doctor_id, patient_id, appointment_id)
        if chat_id:
            logger.info(f"Successfully created test chat with ID: {chat_id}")
    
    # List documents in specific collections
    logger.info("\nTesting document access...")
    list_documents_in_collection(db, "chats")
    list_documents_in_collection(db, "messages")
    
    logger.info("\nFirebase connection test completed!")

if __name__ == "__main__":
    main()