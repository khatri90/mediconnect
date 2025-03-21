from django.urls import path
from .views import DoctorRegistrationAPIView, DoctorRegistrationStatusAPIView, DoctorLoginAPIView, ChangePasswordAPIView, DoctorProfileAPIView


urlpatterns = [
    path('api/doctors/register/', DoctorRegistrationAPIView.as_view(), name='doctor-register'),
    path('api/doctors/status/<int:doctor_id>/', DoctorRegistrationStatusAPIView.as_view(), name='doctor-status'),
    path('api/doctors/login/', DoctorLoginAPIView.as_view(), name='doctor-login'),
    path('api/doctors/change-password/', ChangePasswordAPIView.as_view(), name='doctor-change-password'),
    path('api/doctors/profile/', DoctorProfileAPIView.as_view(), name='doctor-profile'),

]

# mediconnect_project/urls.py

