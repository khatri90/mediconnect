import os
import json
import firebase_admin
from firebase_admin import credentials, storage
from django.core.files.storage import Storage
from django.conf import settings
from urllib.parse import urljoin
from tempfile import NamedTemporaryFile

class FirebaseStorage(Storage):
    def __init__(self):
        # Initialize Firebase if not already initialized
        if not firebase_admin._apps:
            # Load service account credentials from environment variable or settings
            if hasattr(settings, 'FIREBASE_SERVICE_ACCOUNT_JSON') and settings.FIREBASE_SERVICE_ACCOUNT_JSON:
                try:
                    # Try to load JSON from the environment variable
                    service_account_info = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
                    cred = credentials.Certificate(service_account_info)
                except json.JSONDecodeError:
                    # If not a JSON string, assume it's a file path
                    cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
                
                firebase_admin.initialize_app(cred, {
                    'storageBucket': settings.FIREBASE_STORAGE_BUCKET
                })
            else:
                raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON settings variable is not configured properly")
        
        self.bucket = storage.bucket()
        # Custom media path prefix
        self.media_prefix = 'mediconnect/media/'

    def _get_path(self, name):
        """
        Prepend the media prefix to the file path
        """
        return f"{self.media_prefix}{name}"

    def _open(self, name, mode='rb'):
        path = self._get_path(name)
        blob = self.bucket.blob(path)
        
        # Create a temporary file to store the downloaded content
        temp_file = NamedTemporaryFile(delete=False)
        blob.download_to_filename(temp_file.name)
        
        # Open the file and return it
        return open(temp_file.name, mode)

    def _save(self, name, content):
        path = self._get_path(name)
        blob = self.bucket.blob(path)
        
        # Set appropriate content type
        content_type = getattr(content, 'content_type', None)
        if content_type:
            blob.content_type = content_type
        
        # Upload the file
        content.seek(0)
        blob.upload_from_file(content)
        
        # Return the file path without the prefix for Django's internal use
        return name

    def delete(self, name):
        path = self._get_path(name)
        blob = self.bucket.blob(path)
        blob.delete()

    def exists(self, name):
        path = self._get_path(name)
        blob = self.bucket.blob(path)
        return blob.exists()

    def url(self, name):
        """
        Returns the URL where the file can be accessed
        """
        path = self._get_path(name)
        blob = self.bucket.blob(path)
        
        # Generate a public URL with default expiration (typically 7 days)
        return blob.generate_signed_url(
            version='v4',
            expiration=settings.FIREBASE_URL_EXPIRATION,
            method='GET'
        )

    def size(self, name):
        path = self._get_path(name)
        blob = self.bucket.blob(path)
        blob.reload()
        return blob.size

    def get_modified_time(self, name):
        path = self._get_path(name)
        blob = self.bucket.blob(path)
        blob.reload()
        return blob.updated