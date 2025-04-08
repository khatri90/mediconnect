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
from django.http import HttpResponse, FileResponse
import os

def health_check(request):
    return HttpResponse("MediConnect API is running")

def serve_default_image(request, path):
    """Serve a default placeholder image if the requested file doesn't exist"""
    # Check if the requested file exists
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'))
    
    # If it's specifically background.jpg that's missing
    if 'background.jpg' in path:
        # Create a default background.jpg in the doctor_documents directory 
        os.makedirs(os.path.join(settings.MEDIA_ROOT, 'doctor_documents'), exist_ok=True)
        placeholder_path = os.path.join(settings.BASE_DIR, 'staticfiles', 'placeholder.jpg')
        
        # If we have a placeholder in static files, serve it
        if os.path.exists(placeholder_path):
            return FileResponse(open(placeholder_path, 'rb'))
    
    # Return a 404 response but log it with less severity
    return HttpResponse("File not found", status=404)

urlpatterns = [
    path('', health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('api/', include('doctors.urls')),
    path('api/admin/', include('admin_portal.urls')),  # Add this line for admin portal API
    path('media/<path:path>', serve_default_image, name='serve_media'),
]

# For development environment only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
