from django.shortcuts import render
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Doctor, DoctorDocument
from .serializers import DoctorSerializer, DoctorRegistrationSerializer
from django.utils import timezone
from .models import DoctorAccount
from django.contrib.auth.hashers import check_password
from django.conf import settings
import jwt
import datetime

JWT_SECRET = getattr(settings, 'JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_DELTA = datetime.timedelta(days=7)
def generate_token(doctor_id):
    """Generate a JWT token for the doctor"""
    payload = {
        'doctor_id': doctor_id,
        'exp': datetime.datetime.utcnow() + JWT_EXPIRATION_DELTA
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token):
    """Verify a JWT token and return the doctor_id"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('doctor_id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

class DoctorRegistrationAPIView(APIView):
    """
    API view to handle doctor registration
    """
    parser_classes = (MultiPartParser, FormParser)
    
    def post(self, request, format=None):
        serializer = DoctorRegistrationSerializer(data=request.data)
        
        if serializer.is_valid():
            # Create the doctor and related documents
            doctor = serializer.save()
            
            # Return a successful response
            return Response({
                'status': 'success',
                'message': 'Your registration has been submitted successfully and is pending review.',
                'doctor_id': doctor.id
            }, status=status.HTTP_201_CREATED)
            
        return Response({
            'status': 'error',
            'message': 'There was an error with your registration.',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

# If you need to check the status of a registration later
class DoctorRegistrationStatusAPIView(APIView):
    """
    API view to check the status of a doctor registration
    """
    def get(self, request, doctor_id, format=None):
        try:
            doctor = Doctor.objects.get(id=doctor_id)
            return Response({
                'status': 'success',
                'doctor_status': doctor.status,
                'message': f'Your registration is {doctor.get_status_display()}.'
            })
        except Doctor.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Doctor not found.'
            }, status=status.HTTP_404_NOT_FOUND)

class DoctorLoginAPIView(APIView):
    """
    API view to handle doctor login
    """
    def post(self, request, format=None):
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not email or not password:
            return Response({
                'status': 'error',
                'message': 'Email and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Find doctor by email
            doctor = Doctor.objects.get(email=email)
            
            # Check doctor status
            if doctor.status != 'approved':
                return Response({
                    'status': 'error',
                    'message': 'Your account is pending approval'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Find account
            account = DoctorAccount.objects.get(doctor=doctor)
            
            # Verify password
            if not account.check_password(password):
                return Response({
                    'status': 'error',
                    'message': 'Invalid credentials'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Update last login time
            account.last_login = timezone.now()
            account.save(update_fields=['last_login'])
            
            # Get profile photo if available
            profile_photo_url = None
            try:
                profile_photo = DoctorDocument.objects.get(doctor=doctor, document_type='profile_photo')
                profile_photo_url = request.build_absolute_uri(profile_photo.file.url)
            except DoctorDocument.DoesNotExist:
                pass
            
            # Generate JWT token
            token = generate_token(doctor.id)
            
            # Return success response with doctor details and token
            return Response({
                'status': 'success',
                'message': 'Login successful',
                'token': token,
                'doctor_id': doctor.id,
                'name': doctor.full_name,
                'specialty': doctor.specialty,
                'email': doctor.email,
                'location': f"{doctor.city}, {doctor.country}",
                'profile_photo': profile_photo_url
            }, status=status.HTTP_200_OK)
                
        except Doctor.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'No account found for this email'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        except DoctorAccount.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'No account found for this doctor'
            }, status=status.HTTP_401_UNAUTHORIZED)

class ChangePasswordAPIView(APIView):
    """
    API view to handle password changes
    """
    def post(self, request, format=None):
        # Extract data from request
        email = request.data.get('email')
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        
        # Validate input
        if not email or not current_password or not new_password:
            return Response({
                'status': 'error',
                'message': 'All fields are required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Check password requirements
        if len(new_password) < 8:
            return Response({
                'status': 'error',
                'message': 'Password must be at least 8 characters long'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Check if password has at least one number
        if not any(char.isdigit() for char in new_password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one number'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Check if password has at least one uppercase letter
        if not any(char.isupper() for char in new_password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one uppercase letter'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Check if password has at least one symbol
        if not any(not char.isalnum() for char in new_password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one symbol'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Find doctor account by email
            doctor = Doctor.objects.get(email=email)
            account = DoctorAccount.objects.get(doctor=doctor)
            
            # Verify current password
            if not account.check_password(current_password):
                return Response({
                    'status': 'error',
                    'message': 'Current password is incorrect'
                }, status=status.HTTP_401_UNAUTHORIZED)
                
            # Set new password
            account.set_password(new_password)
            
            return Response({
                'status': 'success',
                'message': 'Password updated successfully'
            }, status=status.HTTP_200_OK)
            
        except Doctor.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Doctor not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except DoctorAccount.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Account not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'An error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)            

class DoctorProfileAPIView(APIView):
    """
    API view to retrieve doctor profile information
    """
    def get(self, request, format=None):
        # Get token from authorization header
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return Response({
                'status': 'error',
                'message': 'Authentication token required'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        token = auth_header.split(' ')[1]
        doctor_id = verify_token(token)
        
        if not doctor_id:
            return Response({
                'status': 'error',
                'message': 'Invalid or expired token'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            # Find doctor by ID
            doctor = Doctor.objects.get(id=doctor_id)
            
            # Get profile photo if available
            profile_photo_url = None
            try:
                profile_photo = DoctorDocument.objects.get(doctor=doctor, document_type='profile_photo')
                profile_photo_url = request.build_absolute_uri(profile_photo.file.url)
            except DoctorDocument.DoesNotExist:
                pass
            
            # Return doctor profile data
            return Response({
                'status': 'success',
                'doctor_id': doctor.id,
                'full_name': doctor.full_name,
                'email': doctor.email,
                'specialty': doctor.specialty,
                'location': f"{doctor.city}, {doctor.country}",
                'profile_photo': profile_photo_url
            }, status=status.HTTP_200_OK)
            
        except Doctor.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Doctor not found'
            }, status=status.HTTP_404_NOT_FOUND)
            