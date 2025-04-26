from django.core.management.base import BaseCommand
import os
import json
import firebase_admin
from firebase_admin import credentials, storage
import logging
import requests

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test Firebase Storage configuration'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Testing Firebase Storage configuration...'))
        
        # Check environment variables
        firebase_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
        if not firebase_json:
            self.stdout.write(self.style.ERROR('FIREBASE_SERVICE_ACCOUNT_JSON environment variable not set!'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'FIREBASE_SERVICE_ACCOUNT_JSON is set with {len(firebase_json)} characters'))
        
        from django.conf import settings
        bucket_name = settings.FIREBASE_STORAGE_BUCKET
        if not bucket_name:
            self.stdout.write(self.style.ERROR('FIREBASE_STORAGE_BUCKET environment variable not set!'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'FIREBASE_STORAGE_BUCKET is set to: {bucket_name}'))
        
        # Try to parse the JSON
        try:
            service_account_info = json.loads(firebase_json)
            self.stdout.write(self.style.SUCCESS('Successfully parsed FIREBASE_SERVICE_ACCOUNT_JSON'))
            
            # Print some safe info from the JSON for verification
            if 'project_id' in service_account_info:
                self.stdout.write(self.style.SUCCESS(f'Project ID: {service_account_info["project_id"]}'))
            if 'client_email' in service_account_info:
                email = service_account_info['client_email']
                self.stdout.write(self.style.SUCCESS(f'Client email: {email}'))
            
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {str(e)}'))
            if len(firebase_json) > 100:
                self.stdout.write(self.style.WARNING(f'First 100 chars: {firebase_json[:100]}...'))
            return
        
        # Try to initialize Firebase
        try:
            # Check if Firebase is already initialized
            try:
                app = firebase_admin.get_app()
                self.stdout.write(self.style.SUCCESS('Firebase app already initialized, reusing existing app'))
            except ValueError:
                # App doesn't exist yet, initialize it
                self.stdout.write('Initializing new Firebase app...')
                creds = credentials.Certificate(service_account_info)
                app = firebase_admin.initialize_app(creds, {
                    'storageBucket': bucket_name
                })
                self.stdout.write(self.style.SUCCESS('Successfully initialized Firebase app'))
            
            # Get a reference to the storage bucket
            bucket = storage.bucket(app=app)
            self.stdout.write(self.style.SUCCESS(f'Successfully connected to Firebase Storage bucket: {bucket_name}'))
            
            # Test upload
            self.stdout.write('Testing file upload...')
            
            # Create a temporary text file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.txt') as temp:
                temp.write(b'This is a test file for Firebase Storage')
                temp.seek(0)
                
                # Upload to Firebase
                blob = bucket.blob('test/firebase_test.txt')
                blob.upload_from_file(temp)
            
            self.stdout.write(self.style.SUCCESS('Successfully uploaded test file to Firebase Storage'))
            
            # Generate URL
            url = blob.generate_signed_url(expiration=3600, method='GET')
            self.stdout.write(self.style.SUCCESS(f'Test file URL: {url}'))
            
            # Test URL
            self.stdout.write('Testing URL accessibility...')
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    self.stdout.write(self.style.SUCCESS('URL is accessible! Content can be retrieved.'))
                else:
                    self.stdout.write(self.style.WARNING(f'URL returned status code {response.status_code}'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Error testing URL: {str(e)}'))
            
            # Delete test file
            blob.delete()
            self.stdout.write(self.style.SUCCESS('Successfully deleted test file from Firebase Storage'))
            
            # Test default_storage
            self.stdout.write('\nTesting Django default_storage...')
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            
            storage_class = default_storage.__class__.__name__
            self.stdout.write(f'Current default_storage class: {storage_class}')
            
            if 'Firebase' in storage_class:
                self.stdout.write(self.style.SUCCESS('Django is using Firebase storage!'))
                
                # Test saving a file
                test_path = default_storage.save(
                    'test_django_firebase.txt', 
                    ContentFile('Test content from Django')
                )
                self.stdout.write(f'Saved file to: {test_path}')
                
                # Get URL
                test_url = default_storage.url(test_path)
                self.stdout.write(f'URL from default_storage: {test_url}')
                
                # Delete file
                default_storage.delete(test_path)
                self.stdout.write('Deleted test file from default_storage')
            else:
                self.stdout.write(self.style.WARNING(f'Django is NOT using Firebase storage! Current storage: {storage_class}'))
            
            self.stdout.write(self.style.SUCCESS('\nFIREBASE STORAGE TEST PASSED! Your configuration is working correctly.'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error testing Firebase Storage: {str(e)}'))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
            self.stdout.write(self.style.ERROR('\nFIREBASE STORAGE TEST FAILED! Please check your configuration.'))