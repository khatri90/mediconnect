from django.urls import path
from .views import DoctorRegistrationAPIView, DoctorRegistrationStatusAPIView, DoctorLoginAPIView, ChangePasswordAPIView, DoctorProfileAPIView


urlpatterns = [
    # Removed redundant 'api/' prefix from all paths
    path('doctors/register/', DoctorRegistrationAPIView.as_view(), name='doctor-register'),
    path('doctors/status/<int:doctor_id>/', DoctorRegistrationStatusAPIView.as_view(), name='doctor-status'),
    path('doctors/login/', DoctorLoginAPIView.as_view(), name='doctor-login'),
    path('doctors/change-password/', ChangePasswordAPIView.as_view(), name='doctor-change-password'),
    path('doctors/profile/', DoctorProfileAPIView.as_view(), name='doctor-profile'),
]
