"""
URL configuration for mediconnect_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse, FileResponse, HttpResponseRedirect
import os
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.http import JsonResponse

def health_check(request):
    return HttpResponse("MediConnect API is running")

def serve_default_image(request, path):
    """Modified to work with Firebase Storage"""
    try:
        # Check if the file exists in Firebase Storage
        if default_storage.exists(path):
            # Generate a signed URL and redirect to it
            url = default_storage.url(path)
            return HttpResponseRedirect(url)
        
        # If it's specifically background.jpg that's missing
        if 'background.jpg' in path:
            # Try to serve a placeholder from static files
            placeholder_path = os.path.join(settings.STATIC_ROOT, 'placeholder.jpg')
            if os.path.exists(placeholder_path):
                return FileResponse(open(placeholder_path, 'rb'))
        
        # Return a 404 response
        return HttpResponse("File not found", status=404)
    except Exception as e:
        # Log the error and return a 500 response
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error serving file {path}: {str(e)}")
        return HttpResponse(f"Error serving file: {str(e)}", status=500)

def test_firebase_storage(request):
    """
    Test view to verify Firebase Storage is working correctly.
    """
    try:
        # Create a test file
        test_content = b"Hello, Firebase Storage!"
        path = default_storage.save('test/firebase_test.txt', ContentFile(test_content))
        
        # Get the URL
        url = default_storage.url(path)
        
        # Check if the file exists
        exists = default_storage.exists(path)
        
        return JsonResponse({
            'status': 'success',
            'message': 'Firebase Storage is working!',
            'file_path': path,
            'file_url': url,
            'file_exists': exists
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }, status=500)

urlpatterns = [
    path('', health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('api/', include('doctors.urls')),
    path('api/', include('chat.urls')),  # Add this line for chat URLs
    path('api/admin/', include('admin_portal.urls')),  # Add this line for admin portal API
    path('media/<path:path>', serve_default_image, name='serve_media'),
    path('api/test-firebase/', test_firebase_storage, name='test_firebase_storage'),
]
