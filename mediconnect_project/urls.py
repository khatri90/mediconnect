from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

def health_check(request):
    return HttpResponse("MediConnect API is running")

urlpatterns = [
    path('', health_check, name='health_check'),  # Add this line
    path('admin/', admin.site.urls),
    path('api/', include('doctors.urls')),  # Doctor app APIs
]

# Media files for all environments
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Also serve media files in production
    from django.views.static import serve
    urlpatterns += [
        path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
