# admin_portal/urls.py
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
router.register(r'user-management', views.UserManagementViewSet) 

urlpatterns = [
    # Admin login
    path('login/', views.AdminLoginView.as_view(), name='admin-login'),
    
    # Dashboard statistics
    path('dashboard/stats/', views.AdminDashboardStatsView.as_view(), name='admin-dashboard-stats'),
    
    # Include router URLs
    path('', include(router.urls)),

      path('users/view/', views.view_users, name='view-users'),
    path('api/users/', views.get_users_data, name='get-users-data'),
    path('api/users/<int:user_id>/', views.get_user_details, name='get-user-details'),
    path('api/users/<int:user_id>/toggle-status/', views.toggle_user_status, name='toggle-user-status'),
    path('api/users/<int:user_id>/toggle-admin/', views.toggle_admin_status, name='toggle-admin-status'),
]
