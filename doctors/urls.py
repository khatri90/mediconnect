# doctors/urls.py - Add these URL routes
from .zoom_webhook import zoom_webhook_handler
from django.urls import path
from .views import (
    DoctorRegistrationAPIView, 
    DoctorRegistrationStatusAPIView, 
    DoctorLoginAPIView, 
    ChangePasswordAPIView, 
    DoctorProfileAPIView,
    ApprovedDoctorsAPIView, 
    DoctorAvailabilityAPIView,
    AppointmentSlotAPIView,
    DoctorWeeklyScheduleAPIView,
    PatientAppointmentAPIView,
    CrossApplicationAuthAPIView,
    AppointmentCancelView,
    AppointmentRescheduleView,
    # New dashboard views
    DoctorDashboardStatsAPIView,
    DoctorRevenueChartAPIView,
    DoctorRecentAppointmentsAPIView,
    ReviewAPIView,
    SupportTicketAPIView, 
    FAQAPIView,
    DoctorPatientsAPIView,
    patient_medical_history,
    ZoomMeetingStatusAPIView,
    test_webhook
)

urlpatterns = [
    # Existing paths
    path('doctors/register/', DoctorRegistrationAPIView.as_view(), name='doctor-register'),
    path('doctors/status/<int:doctor_id>/', DoctorRegistrationStatusAPIView.as_view(), name='doctor-status'),
    path('doctors/login/', DoctorLoginAPIView.as_view(), name='doctor-login'),
    path('doctors/change-password/', ChangePasswordAPIView.as_view(), name='doctor-change-password'),
    path('doctors/profile/', DoctorProfileAPIView.as_view(), name='doctor-profile'),
    path('doctors/approved/', ApprovedDoctorsAPIView.as_view(), name='approved-doctors'),
    path('doctors/availability/', DoctorAvailabilityAPIView.as_view(), name='doctor-availability'),
    path('doctors/<int:doctor_id>/schedule/', DoctorWeeklyScheduleAPIView.as_view(), name='doctor-weekly-schedule'),
    
    # Appointment paths
    path('doctors/available-slots/<int:doctor_id>/<str:date>/', AppointmentSlotAPIView.as_view(), name='doctor-available-slots'),
    path('appointments/', PatientAppointmentAPIView.as_view(), name='patient-appointments'),
    path('auth/patient/', CrossApplicationAuthAPIView.as_view(), name='patient-auth'),
    path('appointments/cancel/', AppointmentCancelView.as_view(), name='cancel-appointment'),
    path('appointments/reschedule/', AppointmentRescheduleView.as_view(), name='reschedule-appointment'),
    
    # New dashboard paths
    path('doctors/dashboard/stats/', DoctorDashboardStatsAPIView.as_view(), name='doctor-dashboard-stats'),
    path('doctors/dashboard/revenue-chart/', DoctorRevenueChartAPIView.as_view(), name='doctor-revenue-chart'),
    path('doctors/dashboard/recent-appointments/', DoctorRecentAppointmentsAPIView.as_view(), name='doctor-recent-appointments'),
    
    # Add these to urlpatterns in doctors/urls.py
    path('reviews/', ReviewAPIView.as_view(), name='reviews'),
    path('reviews/<str:appointment_id>/', ReviewAPIView.as_view(), name='appointment-review'),
    path('support/tickets/', SupportTicketAPIView.as_view(), name='support-tickets'),
    path('support/faqs/', FAQAPIView.as_view(), name='faqs'),
    path('doctors/patients/', DoctorPatientsAPIView.as_view(), name='doctor-patients'),
    path('patient-medical-history/<int:patient_id>/', patient_medical_history, name='patient-medical-history'),
    
    path('zoom/webhook/', zoom_webhook_handler, name='zoom-webhook'),
    
    path('meeting/status/', ZoomMeetingStatusAPIView.as_view(), name='meeting-status'),
    
    path('zoom/webhook/test/', test_webhook, name='test-webhook'),
    
    

]
