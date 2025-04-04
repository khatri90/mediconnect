# patients/urls.py - Updated version

from django.urls import path, include
from django.contrib import admin
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for ViewSets
router = DefaultRouter()
router.register(r'medical-records', views.PatientMedicalRecordViewSet, basename='medical-records')

# Make sure admin URLs are properly included
admin.autodiscover()

urlpatterns = [
    # Authentication endpoints
    path('register/', views.PatientRegistrationView.as_view(), name='patient-register'),
    path('login/', views.PatientLoginView.as_view(), name='patient-login'),
    path('profile/', views.PatientProfileView.as_view(), name='patient-profile'),
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot-password'),
    
    # Documents endpoint
    path('documents/', views.PatientDocumentView.as_view(), name='patient-documents'),
    
    # Include router URLs
    path('', include(router.urls)),
]