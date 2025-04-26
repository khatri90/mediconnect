import time
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import os
import json
import logging
import traceback
import firebase_admin
from firebase_admin import credentials, storage
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile


logger = logging.getLogger(__name__)

@csrf_exempt
def debug_upload(request):
    """Debug view to test different upload methods and show detailed diagnostics"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Only GET method is allowed'}, status=405)
    
    # Build a diagnostic response
    try:
        response_html = "<html><body><h1>Firebase Storage Diagnostic</h1>"
        
        # 1. Check Django settings
        response_html += "<h2>Django Storage Settings</h2>"
        response_html += f"<p>DEFAULT_FILE_STORAGE: {settings.DEFAULT_FILE_STORAGE}</p>"
        response_html += f"<p>DEBUG setting: {settings.DEBUG}</p>"
        response_html += f"<p>FIREBASE_STORAGE_BUCKET: {settings.FIREBASE_STORAGE_BUCKET}</p>"
        
        # 2. Check actual storage being used
        response_html += "<h2>Actual Storage in Use</h2>"
        storage_class = default_storage.__class__.__name__
        response_html += f"<p>Storage class: {storage_class}</p>"
        
        if hasattr(default_storage, 'initialized'):
            response_html += f"<p>Storage initialized: {default_storage.initialized}</p>"
        else:
            response_html += "<p>Storage does not have 'initialized' attribute</p>"
            
        if hasattr(default_storage, 'bucket_name'):
            response_html += f"<p>Storage bucket name: {default_storage.bucket_name}</p>"
        
        # 3. Test direct Firebase access
        response_html += "<h2>Direct Firebase Access Test</h2>"
        
        try:
            # Check if Firebase is already initialized
            try:
                app = firebase_admin.get_app()
                response_html += "<p>Firebase app already initialized</p>"
            except ValueError:
                # Initialize Firebase
                response_html += "<p>Initializing new Firebase app...</p>"
                service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
                
                if not service_account_json:
                    response_html += "<p style='color:red'>FIREBASE_SERVICE_ACCOUNT_JSON not set!</p>"
                else:
                    response_html += f"<p>FIREBASE_SERVICE_ACCOUNT_JSON has {len(service_account_json)} characters</p>"
                    
                    # Parse JSON
                    service_account_info = json.loads(service_account_json)
                    
                    # Initialize Firebase
                    creds = credentials.Certificate(service_account_info)
                    app = firebase_admin.initialize_app(creds, {
                        'storageBucket': settings.FIREBASE_STORAGE_BUCKET
                    })
                    response_html += f"<p>Firebase app initialized with bucket: {settings.FIREBASE_STORAGE_BUCKET}</p>"
            
            # Test uploading a file directly
            bucket = storage.bucket(app=app)
            
            # Create a test file
            test_content = f"Test file created at {time.strftime('%Y-%m-%d %H:%M:%S')}"
            test_path = f"debug_test_{int(time.time())}.txt"
            
            # Upload the file
            blob = bucket.blob(test_path)
            blob.upload_from_string(test_content)
            
            # Generate a signed URL
            url = blob.generate_signed_url(expiration=3600, method='GET', version='v4')
            
            response_html += f"<p style='color:green'>Test file successfully uploaded directly to Firebase!</p>"
            response_html += f"<p>Test file path: {test_path}</p>"
            response_html += f"<p>Test file URL: <a href='{url}' target='_blank'>{url}</a></p>"
        
        except Exception as e:
            response_html += f"<p style='color:red'>Error in direct Firebase test: {str(e)}</p>"
            response_html += f"<pre>{traceback.format_exc()}</pre>"
        
        # 4. Test Django storage
        response_html += "<h2>Django Storage Test</h2>"
        
        try:
            # Create test content
            test_content = f"Django storage test file created at {time.strftime('%Y-%m-%d %H:%M:%S')}"
            django_test_path = f"django_test_{int(time.time())}.txt"
            
            # Save using default_storage
            saved_path = default_storage.save(django_test_path, ContentFile(test_content.encode('utf-8')))
            
            response_html += f"<p>File saved to path: {saved_path}</p>"
            
            # Check if the file exists
            exists = default_storage.exists(saved_path)
            response_html += f"<p>File exists in storage: {exists}</p>"
            
            # Get URL
            file_url = default_storage.url(saved_path)
            response_html += f"<p>Generated URL: <a href='{file_url}' target='_blank'>{file_url}</a></p>"
            
            response_html += "<p style='color:green'>Django storage test completed!</p>"
            
        except Exception as e:
            response_html += f"<p style='color:red'>Error in Django storage test: {str(e)}</p>"
            response_html += f"<pre>{traceback.format_exc()}</pre>"
        
        # 5. Final instructions
        response_html += "<h2>What to Check</h2>"
        response_html += "<ol>"
        response_html += "<li>Do both test links work? If direct Firebase works but Django storage doesn't, there's a configuration issue.</li>"
        response_html += "<li>Is the 'Actual Storage in Use' showing 'FirebaseMediaStorage'? If not, Django isn't using Firebase.</li>"
        response_html += "<li>Check your Firebase Storage Rules to ensure write access is enabled.</li>"
        response_html += "</ol>"
        
        response_html += "</body></html>"
        
        return HttpResponse(response_html)
    
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)