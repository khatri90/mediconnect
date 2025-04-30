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
from rest_framework.permissions import IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Q
from user_accounts.models import User  
from .pagination import StandardResultsSetPagination
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
            # Get all doctors and their stats
            total_doctors = Doctor.objects.count()
            pending_doctors = Doctor.objects.filter(status='pending').count()
            approved_doctors = Doctor.objects.filter(status='approved').count()
            rejected_doctors = Doctor.objects.filter(status='rejected').count()
            
            # Get all subscription plans and their counts
            subscription_data = {}
            for plan in Doctor.SUBSCRIPTION_CHOICES:
                plan_code, plan_name = plan
                subscription_data[plan_code] = {
                    'name': plan_name,
                    'count': Doctor.objects.filter(subscription_plan=plan_code).count()
                }
            
            # Calculate subscription revenue
            # These would be your subscription prices, adjust as needed
            subscription_prices = {
                'basic': 29,       # $29/month
                'professional': 49, # $49/month
                'premium': 99      # $99/month
            }
            
            # Calculate monthly subscription revenue
            subscription_revenue = sum(
                subscription_data[plan]['count'] * subscription_prices[plan]
                for plan in subscription_prices
                if plan in subscription_data
            )
            
            # Get total users (patients) - using distinct patient_ids from appointments
            patient_ids = Appointment.objects.values_list('patient_id', flat=True).distinct()
            total_users = len(patient_ids)
            
            # Calculate appointment revenue
            appointment_revenue_data = Appointment.objects.aggregate(
                total_revenue=Sum('amount')
            )
            appointment_revenue = float(appointment_revenue_data['total_revenue'] or 0)
            
            # Total revenue = subscription revenue + appointment revenue
            total_revenue = subscription_revenue + appointment_revenue
            
            # Get monthly revenue data for the chart (last 6 months)
            today = timezone.now().date()
            monthly_data = []
            
            for i in range(5, -1, -1):  # Last 6 months
                # Calculate the first day of the month, i months ago
                month_date = today.replace(day=1)
                for _ in range(i):
                    # Go back one month at a time to handle year boundaries correctly
                    if month_date.month == 1:
                        month_date = month_date.replace(year=month_date.year-1, month=12)
                    else:
                        month_date = month_date.replace(month=month_date.month-1)
                
                # Calculate the last day of the month
                if month_date.month == 12:
                    next_month = month_date.replace(year=month_date.year+1, month=1)
                else:
                    next_month = month_date.replace(month=month_date.month+1)
                
                last_day = (next_month - datetime.timedelta(days=1)).day
                month_end = month_date.replace(day=last_day)
                
                # Get appointments revenue for this month
                month_appointment_revenue = Appointment.objects.filter(
                    appointment_date__gte=month_date,
                    appointment_date__lte=month_end
                ).aggregate(Sum('amount'))['amount__sum'] or 0
                
                # Estimate subscription revenue (this is simplified)
                month_subscription_revenue = subscription_revenue
                
                monthly_data.append({
                    'month': month_date.strftime('%b'),
                    'subscription_revenue': float(month_subscription_revenue),
                    'appointment_revenue': float(month_appointment_revenue),
                    'total_revenue': float(month_subscription_revenue + month_appointment_revenue)
                })
            
            # Count tickets
            total_tickets = SupportTicket.objects.count()
            open_tickets = SupportTicket.objects.filter(
                status__in=['new', 'in_progress']
            ).count()
            
            # Get rating statistics
            reviews = Review.objects.all()
            total_reviews = reviews.count()
            average_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
            
            # Serialize all the statistics
            stats = {
                'total_doctors': total_doctors,
                'pending_doctors': pending_doctors,
                'approved_doctors': approved_doctors,
                'rejected_doctors': rejected_doctors,
                'doctor_verification': {
                    'approved': approved_doctors,
                    'pending': pending_doctors,
                    'rejected': rejected_doctors
                },
                'total_users': total_users,
                'active_subscriptions': total_doctors,
                'subscription_revenue': subscription_revenue,
                'appointment_revenue': appointment_revenue,
                'total_revenue': total_revenue,
                'revenue_chart_data': monthly_data,
                'total_tickets': total_tickets,
                'open_tickets': open_tickets,
                'total_reviews': total_reviews,
                'average_rating': round(average_rating, 2),
                'subscription_data': subscription_data
            }
            
            return Response({
                'status': 'success',
                'stats': stats
            })
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())
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
        
class UserManagementViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing User objects with full CRUD operations
    """
    queryset = User.objects.all().order_by('-date_joined')
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [filters.SearchFilter]
    search_fields = ['email', 'name', 'phone_number']
    
    def get_serializer_class(self):
        """Return appropriate serializer class based on the request"""
        from rest_framework import serializers
        
        class UserManagementSerializer(serializers.ModelSerializer):
            profile_picture_url = serializers.SerializerMethodField()
            
            class Meta:
                model = User
                fields = ('id', 'email', 'name', 'phone_number', 'dob', 'gender', 
                          'profile_picture_url', 'is_active', 'is_staff', 
                          'is_superuser', 'date_joined', 'last_login')
                read_only_fields = ('date_joined', 'last_login')
                
            def get_profile_picture_url(self, obj):
                """Return Firebase URL first, fallback to Django-generated URL."""
                # Use Firebase URL if available
                if obj.profile_picture_firebase_url:
                    return obj.profile_picture_firebase_url
                    
                # Fallback to Django storage URL
                if obj.profile_picture:
                    request = self.context.get('request')
                    return request.build_absolute_uri(obj.profile_picture.url) if request else obj.profile_picture.url
                return None
            
            def create(self, validated_data):
                """Create a new user with encrypted password and return it"""
                password = validated_data.pop('password', None)
                user = User.objects.create_user(**validated_data)
                
                if password:
                    user.set_password(password)
                    user.save()
                    
                return user
            
            def update(self, instance, validated_data):
                """Update a user, setting the password correctly and return it"""
                password = validated_data.pop('password', None)
                profile_picture = validated_data.pop('profile_picture', None)
                
                # Update user fields
                for attr, value in validated_data.items():
                    setattr(instance, attr, value)
                
                # Set new password if provided
                if password:
                    instance.set_password(password)
                
                # Handle profile picture separately
                if profile_picture:
                    instance.profile_picture = profile_picture
                    
                instance.save()
                return instance
        
        return UserManagementSerializer
    
    def get_serializer_context(self):
        """Add request to serializer context for building absolute URLs"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get only active users"""
        active_users = User.objects.filter(is_active=True).order_by('-date_joined')
        page = self.paginate_queryset(active_users)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(active_users, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def admins(self, request):
        """Get only admin users"""
        admin_users = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).order_by('-date_joined')
        page = self.paginate_queryset(admin_users)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(admin_users, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a user account"""
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response({
            'message': f'User {user.email} has been activated'
        })
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a user account"""
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response({
            'message': f'User {user.email} has been deactivated'
        })
    
    @action(detail=True, methods=['post'])
    def make_admin(self, request, pk=None):
        """Make a user an admin"""
        user = self.get_object()
        user.is_staff = True
        user.save()
        return Response({
            'message': f'User {user.email} has been made an admin'
        })
    
    @action(detail=True, methods=['post'])
    def remove_admin(self, request, pk=None):
        """Remove admin privileges from a user"""
        user = self.get_object()
        user.is_staff = False
        user.save()
        return Response({
            'message': f'Admin privileges removed from {user.email}'
        })
