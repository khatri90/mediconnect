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
from rest_framework import viewsets, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Q
from .models import UserProxy
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth.hashers import make_password
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Count
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import UserProxy
from .pagination import StandardResultsSetPagination
import json
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, timedelta
import logging
logger = logging.getLogger(__name__)

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
        
class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination class for admin views"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class UserManagementViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing User objects with full CRUD operations
    """
    queryset = UserProxy.objects.all().order_by('-date_joined')
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
            password = serializers.CharField(write_only=True, required=False)
            
            class Meta:
                model = UserProxy
                fields = ('id', 'email', 'name', 'phone_number', 'dob', 'gender', 
                         'profile_picture_url', 'is_active', 'is_staff', 
                         'is_superuser', 'date_joined', 'last_login', 'password')
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
        
        return UserManagementSerializer
    
    def get_serializer_context(self):
        """Add request to serializer context for building absolute URLs"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def create(self, request, *args, **kwargs):
        """Create a new user"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            # Extract validated data
            data = serializer.validated_data
            
            # Hash the password if provided
            if 'password' in data:
                data['password'] = make_password(data['password'])
            
            # Create the user
            user = UserProxy.objects.create(**data)
            
            # Return the created user
            return Response(
                self.get_serializer(user).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            return Response(
                {'error': f"Error creating user: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def update(self, request, *args, **kwargs):
        """Update a user"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        try:
            # Extract validated data
            data = serializer.validated_data
            
            # Hash the password if provided
            if 'password' in data:
                data['password'] = make_password(data['password'])
            
            # Update each field
            for key, value in data.items():
                setattr(instance, key, value)
            
            # Save the user
            instance.save()
            
            # Return the updated user
            return Response(
                self.get_serializer(instance).data
            )
        except Exception as e:
            logger.error(f"Error updating user: {str(e)}")
            return Response(
                {'error': f"Error updating user: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get only active users"""
        active_users = UserProxy.objects.filter(is_active=True).order_by('-date_joined')
        page = self.paginate_queryset(active_users)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(active_users, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def admins(self, request):
        """Get only admin users"""
        admin_users = UserProxy.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).order_by('-date_joined')
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
def is_admin(user):
    """Check if the user is an admin."""
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_admin)
def view_users(request):
    """Render the user management page."""
    today = datetime.now().strftime('%d %b, %Y')
    return render(request, 'admin_portal/view-users.html', {'today': today})

@login_required
@user_passes_test(is_admin)
def get_users_data(request):
    """API endpoint to get users data for the table."""
    try:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        search = request.GET.get('search', '')
        status_filter = request.GET.get('status', 'all')
        sort_by = request.GET.get('sort_by', 'date_joined')
        sort_order = request.GET.get('sort_order', 'desc')
        
        # Build the queryset
        users_queryset = UserProxy.objects.all()
        
        # Apply search filter
        if search:
            users_queryset = users_queryset.filter(
                name__icontains=search) | users_queryset.filter(
                email__icontains=search) | users_queryset.filter(
                phone_number__icontains=search
            )
        
        # Apply status filter
        if status_filter == 'active':
            users_queryset = users_queryset.filter(is_active=True)
        elif status_filter == 'inactive':
            users_queryset = users_queryset.filter(is_active=False)
        
        # Apply sorting
        if sort_order == 'desc':
            sort_by = f'-{sort_by}'
        users_queryset = users_queryset.order_by(sort_by)
        
        # Count total users
        total_users = users_queryset.count()
        
        # Calculate pagination
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_users = users_queryset[start_index:end_index]
        
        # Get appointment count for each user
        # Here we're getting appointment counts from a hypothetical Appointment model
        # In a real app, adjust this to match your actual models
        from doctors.models import Appointment
        
        users_with_appointments = []
        for user in paginated_users:
            # Count appointments for this user
            appointment_count = Appointment.objects.filter(patient_id=user.id).count()
            
            # Format the date to match the UI expectations
            joined_date = user.date_joined.strftime('%b %d, %Y') if user.date_joined else ''
            
            # Create a user object with all needed data
            user_data = {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'phone_number': user.phone_number or 'N/A',
                'joined_date': joined_date,
                'appointment_count': appointment_count,
                'is_active': user.is_active,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
                'profile_picture_url': user.profile_picture_firebase_url or '',
            }
            users_with_appointments.append(user_data)
        
        # Get user statistics
        total_active_users = UserProxy.objects.filter(is_active=True).count()
        total_inactive_users = total_users - total_active_users
        total_blocked_users = total_inactive_users  # For simplicity, we're treating inactive as blocked
        
        # Calculate new users this week
        one_week_ago = datetime.now() - timedelta(days=7)
        new_users_this_week = UserProxy.objects.filter(date_joined__gte=one_week_ago).count()
        
        # Get total appointments
        total_appointments = Appointment.objects.count()
        
        # Prepare response data
        response_data = {
            'users': users_with_appointments,
            'total_users': total_users,
            'total_active_users': total_active_users,
            'total_inactive_users': total_inactive_users,
            'total_blocked_users': total_blocked_users,
            'new_users_this_week': new_users_this_week,
            'total_appointments': total_appointments,
            'current_page': page,
            'total_pages': (total_users + page_size - 1) // page_size,  # Ceiling division
            'page_size': page_size,
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def toggle_user_status(request, user_id):
    """API endpoint to toggle user active status."""
    try:
        data = json.loads(request.body)
        action = data.get('action', '')
        
        user = UserProxy.objects.get(id=user_id)
        
        if action == 'activate':
            user.is_active = True
            message = f"User {user.name} has been activated successfully"
        elif action == 'deactivate':
            user.is_active = False
            message = f"User {user.name} has been deactivated successfully"
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)
        
        user.save()
        
        return JsonResponse({'status': 'success', 'message': message})
        
    except UserProxy.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def toggle_admin_status(request, user_id):
    """API endpoint to toggle user admin status."""
    try:
        data = json.loads(request.body)
        action = data.get('action', '')
        
        user = UserProxy.objects.get(id=user_id)
        
        if action == 'make_admin':
            user.is_staff = True
            message = f"User {user.name} has been made an admin successfully"
        elif action == 'remove_admin':
            user.is_staff = False
            message = f"Admin privileges removed from {user.name} successfully"
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)
        
        user.save()
        
        return JsonResponse({'status': 'success', 'message': message})
        
    except UserProxy.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin)
def get_user_details(request, user_id):
    """API endpoint to get detailed information about a specific user."""
    try:
        user = UserProxy.objects.get(id=user_id)
        
        # Get user appointments
        from doctors.models import Appointment, Doctor
        
        appointments = Appointment.objects.filter(patient_id=user.id).order_by('-appointment_date')[:10]
        
        appointment_data = []
        for appt in appointments:
            doctor_name = f"Dr. {appt.doctor.first_name} {appt.doctor.last_name}" if appt.doctor else "N/A"
            
            appointment_data.append({
                'id': appt.id,
                'doctor_name': doctor_name,
                'doctor_id': appt.doctor_id,
                'date': appt.appointment_date.strftime('%d %b, %Y') if appt.appointment_date else '',
                'time': appt.start_time.strftime('%I:%M %p') if appt.start_time else '',
                'type': appt.appointment_type,
                'status': appt.status,
            })
        
        # Format the user details
        user_data = {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'phone_number': user.phone_number or 'N/A',
            'gender': user.gender,
            'gender_display': 'Male' if user.gender == 'M' else ('Female' if user.gender == 'F' else 'Other'),
            'dob': user.dob.strftime('%d %b, %Y') if user.dob else 'N/A',
            'age': calculate_age(user.dob) if user.dob else 'N/A',
            'joined_date': user.date_joined.strftime('%d %b, %Y') if user.date_joined else '',
            'last_login': user.last_login.strftime('%d %b, %Y') if user.last_login else 'Never',
            'is_active': user.is_active,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'profile_picture_url': user.profile_picture_firebase_url or '',
            'appointments': appointment_data,
            'appointment_count': len(appointment_data),
        }
        
        return JsonResponse(user_data)
        
    except UserProxy.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def calculate_age(born):
    """Calculate age from date of birth"""
    today = datetime.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
