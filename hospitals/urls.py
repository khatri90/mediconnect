from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for ViewSets
router = DefaultRouter()
router.register(r'hospitals', views.HospitalViewSet)
router.register(r'departments', views.DepartmentViewSet, basename='departments')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
]