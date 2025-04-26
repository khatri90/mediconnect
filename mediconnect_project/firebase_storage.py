import os
import json
import uuid
import firebase_admin
from firebase_admin import credentials, storage
from django.core.files.storage import Storage
from django.conf import settings
import logging
import traceback
import time

logger = logging.getLogger(__name__)

class FirebaseStorage(Storage):
    """
    Django storage backend for Firebase Cloud Storage
    """
    def __init__(self, *args, **kwargs):
        # The Django Storage base class doesn't accept args/kwargs
        Storage.__init__(self)
        
        # Get initialization parameters
        self.location = kwargs.get('location', 'mediconnect/media')
        self.file_overwrite = kwargs.get('file_overwrite', False)
        self.initialized = False
        self.bucket = None
        self.initialization_attempts = 0
        self.max_initialization_attempts = 3
        
        # Try to initialize Firebase immediately
        self._init_firebase()
        
    def _init_firebase(self):
        """Initialize Firebase Admin SDK if not already initialized"""
        if self.initialized and self.bucket:
            return True
            
        # Limit retries to avoid infinite loops
        self.initialization_attempts += 1
        if self.initialization_attempts > self.max_initialization_attempts:
            logger.error(f"Failed to initialize Firebase after {self.max_initialization_attempts} attempts. Giving up.")
            return False
            
        try:
            # Get service account credentials from environment variable
            service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
            if not service_account_json:
                logger.error("FIREBASE_SERVICE_ACCOUNT_JSON environment variable not set")
                return False
            
            # Log a small portion of the JSON to verify it's available (don't log credentials!)
            logger.info(f"FIREBASE_SERVICE_ACCOUNT_JSON available: {len(service_account_json)} characters")
            
            # Parse the JSON string to a Python dictionary
            try:
                service_account_info = json.loads(service_account_json)
                logger.info("Successfully parsed FIREBASE_SERVICE_ACCOUNT_JSON")
                
                # Print some safe parts of the credentials for verification
                if 'project_id' in service_account_info:
                    logger.info(f"Firebase project_id: {service_account_info['project_id']}")
                if 'client_email' in service_account_info:
                    client_email = service_account_info['client_email']
                    # Only show the domain part of the email for security
                    email_parts = client_email.split('@')
                    if len(email_parts) > 1:
                        logger.info(f"Firebase client_email domain: @{email_parts[1]}")
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {str(e)}")
                if len(service_account_json) > 100:
                    # Show truncated beginning to help debug
                    logger.error(f"First 100 chars: {service_account_json[:100]}...")
                else:
                    logger.error(f"Content: {service_account_json}")
                return False
            
            # Get bucket name from environment variable
            self.bucket_name = os.environ.get('FIREBASE_STORAGE_BUCKET')
            if not self.bucket_name:
                logger.error("FIREBASE_STORAGE_BUCKET environment variable not set")
                return False
            
            logger.info(f"Initializing Firebase Storage with bucket: {self.bucket_name}")
            
            # Initialize Firebase Admin SDK if not already initialized
            try:
                # Check if Firebase is already initialized
                try:
                    self.app = firebase_admin.get_app()
                    logger.info("Firebase app already initialized, reusing existing app")
                except ValueError:
                    # App doesn't exist yet, initialize it
                    logger.info("Initializing new Firebase app")
                    creds = credentials.Certificate(service_account_info)
                    self.app = firebase_admin.initialize_app(creds, {
                        'storageBucket': self.bucket_name
                    })
                
                # Get a reference to the storage bucket
                self.bucket = storage.bucket(app=self.app)
                logger.info(f"Firebase Storage initialized with bucket: {self.bucket_name}")
                
                # Test the connection by listing blobs
                try:
                    blobs = list(self.bucket.list_blobs(max_results=1))
                    logger.info(f"Successfully connected to bucket, found {len(blobs)} blobs")
                except Exception as e:
                    logger.error(f"Could connect to bucket but got error when listing blobs: {str(e)}")
                    # Continue anyway as this might be an empty bucket
                
                self.initialized = True
                return True
            except Exception as e:
                logger.error(f"Error initializing Firebase app: {str(e)}")
                logger.error(traceback.format_exc())
                
                # Wait a bit before potentially retrying
                time.sleep(1)
                return False
        except Exception as e:
            logger.error(f"Unexpected error in _init_firebase: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def _ensure_initialized(self):
        """Make sure Firebase is initialized before any operation"""
        if not self.initialized:
            if not self._init_firebase():
                raise ValueError("Firebase Storage failed to initialize. Check logs for details.")
    
    def _get_storage_path(self, name):
        """
        Get the full storage path for a file, including the location prefix
        """
        return os.path.join(self.location, name) if self.location else name

    def _open(self, name, mode='rb'):
        """
        Open a file from Firebase Storage
        """
        self._ensure_initialized()
        
        path = self._get_storage_path(name)
        blob = self.bucket.blob(path)
        
        logger.info(f"Opening file from Firebase: {path}")
        
        # Create a temporary file to store the downloaded content
        import tempfile
        temp_file = tempfile.TemporaryFile()
        
        try:
            blob.download_to_file(temp_file)
            temp_file.seek(0)
            return temp_file
        except Exception as e:
            temp_file.close()
            logger.error(f"Error opening file {path} from Firebase Storage: {str(e)}")
            raise

    def _save(self, name, content):
        """
        Save a file to Firebase Storage with enhanced error checking and debugging
        """
        self._ensure_initialized()
        
        # Log more details
        logger.info(f"Attempting to save file {name} to Firebase Storage")
        logger.info(f"Using bucket: {self.bucket_name}")
        
        # If file_overwrite is False, generate a unique filename
        if not self.file_overwrite:
            name = self._get_unique_filename(name)
        
        path = self._get_storage_path(name)
        logger.info(f"Full storage path: {path}")
        
        try:
            # Get a reference to the blob
            blob = self.bucket.blob(path)
            
            # Set content type based on file extension
            content_type = self._get_content_type(name)
            if content_type:
                blob.content_type = content_type
                logger.info(f"Content type set to: {content_type}")
            
            # Try to get file details
            try:
                file_size = content.size
                logger.info(f"File size: {file_size} bytes")
            except AttributeError:
                logger.info("Couldn't determine file size")
            
            # Reset file cursor to beginning
            if hasattr(content, 'seek'):
                content.seek(0)
            
            # For debugging, log parts of the file (for small text files)
            try:
                if hasattr(content, 'read') and hasattr(content, 'seek') and content_type and 'text' in content_type:
                    preview = content.read(100)  # Read first 100 bytes
                    logger.info(f"File content preview: {preview}")
                    content.seek(0)  # Reset position
            except Exception as e:
                logger.info(f"Couldn't preview file content: {e}")
            
            # Try the upload with several methods in case one fails
            upload_success = False
            
            # Method 1: Use upload_from_file (Django's common method)
            try:
                logger.info("Attempting upload_from_file...")
                blob.upload_from_file(content)
                upload_success = True
                logger.info("upload_from_file succeeded!")
            except Exception as e:
                logger.error(f"Error with upload_from_file: {e}")
                
                # Method 2: If content can be read completely, try upload_from_string
                if not upload_success and hasattr(content, 'read') and hasattr(content, 'seek'):
                    try:
                        logger.info("Attempting upload_from_string...")
                        content.seek(0)
                        file_data = content.read()
                        blob.upload_from_string(file_data, content_type=content_type)
                        upload_success = True
                        logger.info("upload_from_string succeeded!")
                    except Exception as e:
                        logger.error(f"Error with upload_from_string: {e}")
            
            # Verify that the upload actually worked
            if upload_success:
                try:
                    exists = blob.exists()
                    logger.info(f"Blob exists check after upload: {exists}")
                    if exists:
                        logger.info(f"File {path} successfully uploaded and verified in Firebase Storage")
                        return name
                    else:
                        logger.error(f"Upload appeared successful but file does not exist in bucket!")
                        raise Exception("File upload verification failed - file not found in bucket")
                except Exception as e:
                    logger.error(f"Error verifying upload: {e}")
                    raise
            else:
                logger.error("All upload methods failed")
                raise Exception("All upload methods failed")
                
        except Exception as e:
            logger.error(f"Error saving file {path} to Firebase Storage: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
            
    def _get_unique_filename(self, name):
        """
        Generate a unique filename by adding a UUID if file exists
        """
        # Extract directory and filename
        dirname, filename = os.path.split(name)
        
        # Extract filename and extension
        name_without_ext, ext = os.path.splitext(filename)
        
        # Add a UUID to make the filename unique
        unique_name = f"{name_without_ext}_{uuid.uuid4().hex[:8]}{ext}"
        
        # Join directory and new filename
        return os.path.join(dirname, unique_name)
    
    def _get_content_type(self, name):
        """
        Get the content type for a file based on its extension
        """
        import mimetypes
        return mimetypes.guess_type(name)[0]
    
    def delete(self, name):
        """
        Delete a file from Firebase Storage
        """
        if not self._init_firebase():
            logger.error("Firebase storage not initialized during delete operation")
            return  # Silently fail
        
        path = self._get_storage_path(name)
        blob = self.bucket.blob(path)
        
        try:
            blob.delete()
            logger.info(f"File {path} deleted from Firebase Storage")
        except Exception as e:
            logger.error(f"Error deleting file {path} from Firebase Storage: {str(e)}")
    
    def exists(self, name):
        """
        Check if a file exists in Firebase Storage
        """
        if not self._init_firebase():
            logger.error("Firebase storage not initialized during exists check")
            return False
        
        path = self._get_storage_path(name)
        blob = self.bucket.blob(path)
        
        try:
            return blob.exists()
        except Exception as e:
            logger.error(f"Error checking if file {path} exists in Firebase Storage: {str(e)}")
            return False
    
    def size(self, name):
        """
        Get the size of a file in Firebase Storage
        """
        self._ensure_initialized()
        
        path = self._get_storage_path(name)
        blob = self.bucket.blob(path)
        
        try:
            blob.reload()
            return blob.size
        except Exception as e:
            logger.error(f"Error getting size of file {path} from Firebase Storage: {str(e)}")
            raise
    
    def url(self, name):
        """
        Get the URL for a file in Firebase Storage with proper authentication
        """
        if not self._init_firebase():
            logger.error("Firebase storage not initialized when generating URL")
            # Return a placeholder URL that indicates the error
            return f"/media-not-available/{name}"
        
        path = self._get_storage_path(name)
        blob = self.bucket.blob(path)
        
        try:
            # Check if blob exists
            if not blob.exists():
                logger.warning(f"File {path} does not exist in Firebase Storage bucket")
                return f"/media-not-available/{name}"
            
            # Generate a signed URL that expires in 7 days (604800 seconds)
            logger.info(f"Generating signed URL for {path}")
            url = blob.generate_signed_url(
                expiration=604800,  # 7 days
                method='GET',
                version='v4',  # Use v4 signing for better compatibility
            )
            logger.info(f"Generated signed URL: {url[:50]}...")  # Log part of the URL
            return url
        except Exception as e:
            logger.error(f"Error generating signed URL for file {path}: {str(e)}")
            
            # Use Firebase Storage URL format instead of Google Cloud Storage
            try:
                # This is the Firebase Storage URL format with escaped path
                encoded_path = path.replace('/', '%2F')
                fallback_url = f"https://firebasestorage.googleapis.com/v0/b/{self.bucket_name}/o/{encoded_path}?alt=media"
                logger.info(f"Using Firebase Storage fallback URL: {fallback_url}")
                return fallback_url
            except Exception as fallback_error:
                logger.error(f"Error generating fallback URL: {str(fallback_error)}")
                return f"/media-not-available/{name}"
                
    def get_available_name(self, name, max_length=None):
        """
        Return a filename that's free on the target storage system
        """
        # If file_overwrite is True, we'll overwrite the file
        if self.file_overwrite:
            return name
        
        # Otherwise, generate a unique name
        return super().get_available_name(name, max_length)


class FirebaseMediaStorage(FirebaseStorage):
    """
    Storage for media files
    """
    def __init__(self, *args, **kwargs):
        kwargs['location'] = 'mediconnect/media'
        FirebaseStorage.__init__(self, *args, **kwargs)