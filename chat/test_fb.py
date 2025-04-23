#!/usr/bin/env python3
"""
Test script for Firebase chat functionality - Read Only Version
Run this script to test if Firebase connection works correctly
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

def initialize_firebase(service_account_path):
    """Initialize Firebase with a service account file"""
    try:
        # Try to get an existing app
        app = firebase_admin.get_app()
        logger.info("Using existing Firebase app")
    except ValueError:
        # Initialize with the provided service account file
        logger.info(f"Initializing Firebase with service account: {service_account_path}")
        try:
            creds = credentials.Certificate(service_account_path)
            app = firebase_admin.initialize_app(creds)
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
        for collection in collections:
            logger.info(f"- {collection.id}")
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
        
        if doc_count == 0:
            logger.info(f"No documents found in '{collection_name}' collection")
        
        return True
    except Exception as e:
        logger.error(f"Error listing documents in '{collection_name}': {e}")
        return False

def main():
    """Test the Firebase connection by reading from the database"""
    logger.info("=== Firebase Connection Test (Read Only) ===")
    
    # Get the service account file path
    service_account_path = input("Enter the path to the Firebase service account JSON file: ")
    if not os.path.exists(service_account_path):
        logger.error(f"File not found: {service_account_path}")
        return
    
    # Initialize Firebase
    db = initialize_firebase(service_account_path)
    if not db:
        logger.error("Failed to initialize Firebase")
        return
    
    # List all collections
    logger.info("\nTesting collection access...")
    if not list_collections(db):
        return
    
    # List documents in specific collections
    logger.info("\nTesting document access...")
    list_documents_in_collection(db, "chats")
    list_documents_in_collection(db, "messages")
    
    logger.info("\nFirebase connection test completed successfully!")

if __name__ == "__main__":
    main()