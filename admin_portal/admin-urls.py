from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.AdminUserViewSet)
router.register(r'doctors', views.AdminDoctorViewSet)
router.register(r'faqs', views.AdminFAQViewSet)
router.register(r'tickets', views.AdminSupportTicketViewSet)
router.register(r'reviews', views.AdminReviewViewSet)
router.register(r'appointments', views.AdminAppointmentViewSet)

urlpatterns = [
    # Admin login
    path('login/', views.AdminLoginView.as_view(), name='admin-login'),
    
    # Dashboard statistics
    path('dashboard/stats/', views.AdminDashboardStatsView.as_view(), name='admin-dashboard-stats'),
    
    # Include router URLs
    path('', include(router.urls)),
]
