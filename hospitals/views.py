from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404

from .models import Hospital, Department
from .serializers import (
    HospitalSerializer, 
    HospitalListSerializer,
    DepartmentSerializer,
    HospitalWithDepartmentsSerializer
)

class HospitalViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows hospitals to be viewed or edited.
    """
    queryset = Hospital.objects.all().order_by('name')
    parser_classes = [MultiPartParser, FormParser]
    
    def get_serializer_class(self):
        """
        Return appropriate serializer based on action
        """
        if self.action == 'list':
            return HospitalListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return HospitalWithDepartmentsSerializer
        return HospitalSerializer
    
    def get_serializer_context(self):
        """
        Add request to serializer context for building absolute image URLs
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def get_permissions(self):
        """
        Only staff users can create/update/delete hospitals
        Anyone can view hospital data
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAdminUser]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]
    
    @action(detail=True, methods=['get'])
    def departments(self, request, pk=None):
        """
        Get departments for a specific hospital
        """
        hospital = self.get_object()
        departments = hospital.departments.all()
        serializer = DepartmentSerializer(departments, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def add_department(self, request, pk=None):
        """
        Add a department to a hospital
        """
        hospital = self.get_object()
        serializer = DepartmentSerializer(data=request.data)
        
        if serializer.is_valid():
            serializer.save(hospital=hospital)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def by_city(self, request):
        """
        Filter hospitals by city
        """
        city = request.query_params.get('city', None)
        
        if city:
            hospitals = Hospital.objects.filter(city__icontains=city)
            serializer = HospitalListSerializer(hospitals, many=True, context={'request': request})
            return Response(serializer.data)
        
        return Response({"error": "City parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Search hospitals by name, city, or specialties
        """
        query = request.query_params.get('q', None)
        
        if query:
            hospitals = Hospital.objects.filter(
                name__icontains=query
            ) | Hospital.objects.filter(
                city__icontains=query
            ) | Hospital.objects.filter(
                specialties__icontains=query
            )
            
            serializer = HospitalListSerializer(hospitals, many=True, context={'request': request})
            return Response(serializer.data)
        
        return Response({"error": "Search query parameter 'q' is required"}, status=status.HTTP_400_BAD_REQUEST)

class DepartmentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows departments to be viewed or edited.
    """
    serializer_class = DepartmentSerializer
    
    def get_queryset(self):
        """
        Optionally restricts the returned departments to a given hospital,
        by filtering against a `hospital` query parameter in the URL.
        """
        queryset = Department.objects.all()
        hospital_id = self.request.query_params.get('hospital', None)
        
        if hospital_id is not None:
            queryset = queryset.filter(hospital__id=hospital_id)
        
        return queryset
    
    def get_permissions(self):
        """
        Only staff users can create/update/delete departments
        Anyone can view department data
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAdminUser]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]