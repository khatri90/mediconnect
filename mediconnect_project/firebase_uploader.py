import os
import json
import firebase_admin
from firebase_admin import credentials, storage
import uuid
import logging
import traceback
from django.conf import settings

logger = logging.getLogger(__name__)

class DirectFirebaseUploader:
    """
    Utility class to handle direct uploads to Firebase Storage,
    bypassing Django's storage system completely.
    """
    
    @staticmethod
    def get_bucket():
        """Get a reference to the Firebase Storage bucket."""
        try:
            # Check if Firebase is already initialized
            try:
                app = firebase_admin.get_app()
                logger.info("Using existing Firebase app")
            except ValueError:
                # Initialize Firebase
                logger.info("Initializing new Firebase app")
                service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
                if not service_account_json:
                    logger.error("FIREBASE_SERVICE_ACCOUNT_JSON environment variable not set")
                    return None
                
                service_account_info = json.loads(service_account_json)
                bucket_name = settings.FIREBASE_STORAGE_BUCKET
                
                creds = credentials.Certificate(service_account_info)
                app = firebase_admin.initialize_app(creds, {
                    'storageBucket': bucket_name
                })
            
            # Get bucket reference
            bucket = storage.bucket(app=app)
            return bucket
        
        except Exception as e:
            logger.error(f"Error getting Firebase bucket: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    @staticmethod
    def upload_file(file_obj, destination_path):
        """
        Upload a file directly to Firebase Storage.
        
        Args:
            file_obj: File-like object to upload
            destination_path: Path in Firebase Storage
            
        Returns:
            (success, url): Tuple with success flag and URL if successful
        """
        try:
            if not file_obj:
                logger.warning("No file provided for upload")
                return False, None
            
            # Generate a unique filename if not specified
            if not destination_path:
                file_extension = os.path.splitext(file_obj.name)[1] if hasattr(file_obj, 'name') else ''
                destination_path = f"uploads/{uuid.uuid4().hex}{file_extension}"
            
            logger.info(f"Uploading file to Firebase: {destination_path}")
            
            # Get bucket
            bucket = DirectFirebaseUploader.get_bucket()
            if not bucket:
                logger.error("Failed to get Firebase bucket")
                return False, None
            
            # Create a blob reference
            blob = bucket.blob(destination_path)
            
            # Get content type
            content_type = None
            if hasattr(file_obj, 'content_type'):
                content_type = file_obj.content_type
            
            # Upload the file
            if hasattr(file_obj, 'read'):
                # Reset cursor position
                if hasattr(file_obj, 'seek'):
                    file_obj.seek(0)
                
                # Upload from file
                blob.upload_from_file(file_obj, content_type=content_type)
            elif isinstance(file_obj, bytes):
                # Upload from bytes
                blob.upload_from_string(file_obj, content_type=content_type)
            else:
                # Try generic upload (might not work for all cases)
                blob.upload_from_file(file_obj)
            
            logger.info(f"File uploaded successfully to Firebase: {destination_path}")
            
            # Generate a URL
            url = blob.generate_signed_url(
                expiration=604800,  # 7 days in seconds
                method='GET',
                version='v4'
            )
            
            return True, url
        
        except Exception as e:
            logger.error(f"Error uploading file to Firebase: {str(e)}")
            logger.error(traceback.format_exc())
            return False, None
    
    @staticmethod
    def delete_file(file_path):
        """Delete a file from Firebase Storage."""
        try:
            if not file_path:
                return False
            
            logger.info(f"Deleting file from Firebase: {file_path}")
            
            # Get bucket
            bucket = DirectFirebaseUploader.get_bucket()
            if not bucket:
                return False
            
            # Delete the file
            blob = bucket.blob(file_path)
            blob.delete()
            
            logger.info(f"File deleted successfully from Firebase: {file_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error deleting file from Firebase: {str(e)}")
            logger.error(traceback.format_exc())
            return False