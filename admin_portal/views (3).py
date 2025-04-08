from django.shortcuts import render, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db.models import Count, Avg, Q
from django.utils import timezone
from rest_framework import viewsets, permissions, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from doctors.models import Doctor, FAQ, SupportTicket, Review, Appointment
from .serializers import (
    AdminUserSerializer,
    AdminDoctorSerializer,
    AdminDoctorListSerializer,
    AdminFAQSerializer,
    AdminSupportTicketSerializer,
    AdminReviewSerializer,
    AdminAppointmentSerializer,
    AdminDashboardStatsSerializer
)
import jwt
import datetime
from django.conf import settings

JWT_SECRET = getattr(settings, 'JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_DELTA = datetime.timedelta(days=1)  # Admin tokens expire in 1 day

def generate_admin_token(user_id):
    """Generate a JWT token for admin users"""
    payload = {
        'user_id': user_id,
        'is_admin': True,
        'exp': datetime.datetime.utcnow() + JWT_EXPIRATION_DELTA
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_admin_token(token):
    """Verify a JWT token and ensure it's an admin token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # Check if it's an admin token
        if not payload.get('is_admin', False):
            return None
        return payload.get('user_id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users with valid tokens
    """
    def has_permission(self, request, view):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return False
            
        token = auth_header.split(' ')[1]
        user_id = verify_admin_token(token)
        
        if not user_id:
            return False
            
        try:
            user = User.objects.get(id=user_id)
            return user.is_staff or user.is_superuser
        except User.DoesNotExist:
            return False

class AdminLoginView(APIView):
    """API view to authenticate admin users and return a token"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, format=None):
        username = request.data.get('username')
        password = request.data.get('password')
        
        if not username or not password:
            return Response({
                'status': 'error',
                'message': 'Username and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Authenticate the user
            user = authenticate(username=username, password=password)
            
            if not user:
                return Response({
                    'status': 'error',
                    'message': 'Invalid credentials'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Check if user is an admin
            if not (user.is_staff or user.is_superuser):
                return Response({
                    'status': 'error',
                    'message': 'You do not have admin permissions'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Generate JWT token
            token = generate_admin_token(user.id)
            
            # Return success response with token and user details
            return Response({
                'status': 'success',
                'token': token,
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'name': f"{user.first_name} {user.last_name}",
                'is_superuser': user.is_superuser
            }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination class for admin views"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class AdminDashboardStatsView(APIView):
    """API view to get dashboard statistics"""
    permission_classes = [IsAdminUser]
    
    def get(self, request, format=None):
        try:
            # Calculate various statistics
            total_doctors = Doctor.objects.count()
            pending_doctors = Doctor.objects.filter(status='pending').count()
            total_appointments = Appointment.objects.count()
            total_tickets = SupportTicket.objects.count()
            open_tickets = SupportTicket.objects.filter(
                status__in=['new', 'in_progress']
            ).count()
            
            # Get rating statistics
            reviews = Review.objects.all()
            total_reviews = reviews.count()
            average_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
            
            # Serialize the statistics
            stats = {
                'total_doctors': total_doctors,
                'pending_doctors': pending_doctors,
                'total_appointments': total_appointments,
                'total_tickets': total_tickets,
                'open_tickets': open_tickets,
                'total_reviews': total_reviews,
                'average_rating': round(average_rating, 2)
            }
            
            serializer = AdminDashboardStatsSerializer(stats)
            
            return Response({
                'status': 'success',
                'stats': serializer.data
            })
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AdminUserViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Django User objects"""
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']
    
    @action(detail=False, methods=['get'])
    def admins(self, request):
        """Get only admin users"""
        admins = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True))
        page = self.paginate_queryset(admins)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(admins, many=True)
        return Response(serializer.data)

class AdminDoctorViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Doctor objects"""
    queryset = Doctor.objects.all().order_by('-created_at')
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['first_name', 'last_name', 'email', 'specialty', 'license_number']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return AdminDoctorListSerializer
        return AdminDoctorSerializer
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get only pending doctors"""
        pending = Doctor.objects.filter(status='pending').order_by('-created_at')
        page = self.paginate_queryset(pending)
        
        if page is not None:
            serializer = AdminDoctorListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = AdminDoctorListSerializer(pending, many=True)
        return Response(serializer.data)
        
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a doctor"""
        doctor = self.get_object()
        doctor.status = 'approved'
        doctor.save()
        return Response({
            'status': 'success',
            'message': f'Doctor {doctor.full_name} has been approved'
        })
        
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a doctor"""
        doctor = self.get_object()
        doctor.status = 'rejected'
        doctor.save()
        return Response({
            'status': 'success',
            'message': f'Doctor {doctor.full_name} has been rejected'
        })

class AdminFAQViewSet(viewsets.ModelViewSet):
    """ViewSet for managing FAQ objects"""
    queryset = FAQ.objects.all().order_by('order', 'category')
    serializer_class = AdminFAQSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['question', 'answer', 'category']

class AdminSupportTicketViewSet(viewsets.ModelViewSet):
    """ViewSet for managing SupportTicket objects"""
    queryset = SupportTicket.objects.all().order_by('-created_at')
    serializer_class = AdminSupportTicketSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['ticket_id', 'full_name', 'email', 'message', 'subject']
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark a ticket as resolved"""
        ticket = self.get_object()
        ticket.status = 'resolved'
        ticket.resolved_at = timezone.now()
        
        # Add response if provided
        if 'response' in request.data:
            ticket.response = request.data['response']
            
        ticket.save()
        return Response({
            'status': 'success',
            'message': f'Ticket {ticket.ticket_id} has been resolved'
        })
        
    @action(detail=False, methods=['get'])
    def open(self, request):
        """Get only open tickets"""
        open_tickets = SupportTicket.objects.filter(
            status__in=['new', 'in_progress']
        ).order_by('-created_at')
        
        page = self.paginate_queryset(open_tickets)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(open_tickets, many=True)
        return Response(serializer.data)

class AdminReviewViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Review objects"""
    queryset = Review.objects.all().order_by('-created_at')
    serializer_class = AdminReviewSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['doctor__first_name', 'doctor__last_name', 'review_text']

class AdminAppointmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Appointment objects"""
    queryset = Appointment.objects.all().order_by('-appointment_date', '-start_time')
    serializer_class = AdminAppointmentSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['appointment_id', 'doctor__first_name', 'doctor__last_name', 
                     'patient_name', 'patient_email']
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get only upcoming appointments"""
        today = timezone.now().date()
        upcoming = Appointment.objects.filter(
            appointment_date__gte=today,
            status__in=['pending', 'confirmed']
        ).order_by('appointment_date', 'start_time')
        
        page = self.paginate_queryset(upcoming)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(upcoming, many=True)
        return Response(serializer.data)
