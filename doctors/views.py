from django.shortcuts import render, get_object_or_404
from rest_framework import status, permissions 
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Doctor, DoctorDocument, DoctorAccount, Review
from .serializers import DoctorSerializer, DoctorRegistrationSerializer, ReviewSerializer
from django.utils import timezone
from django.contrib.auth.hashers import check_password
from django.conf import settings
from django.http import HttpResponse
import jwt
import datetime
from datetime import datetime as dt  # Add this import for datetime.strptime
from django.db import transaction
from .models import Doctor, DoctorAvailability, DoctorAvailabilitySettings
from .serializers import (
    DoctorAvailabilitySerializer, 
    DoctorAvailabilitySettingsSerializer,
    DoctorAvailabilityUpdateSerializer
)
import json
import traceback
from django.db import models
from django.db.models import Q, Avg
from .models import Appointment
from .serializers import AppointmentSerializer, AppointmentCreateSerializer
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.http import JsonResponse
from django.db.models import Count, Sum
from django.utils import timezone
from django.db.models.functions import TruncMonth
from .models import Doctor, Appointment, DoctorAccount
from .models import FAQ, SupportTicket
from .serializers import SupportTicketCreateSerializer
from .serializers import SupportTicketSerializer
from .serializers import FAQSerializer
import requests
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .appointment_service import AppointmentService

def test_webhook(request):
    """Simple view to test webhook URL routing"""
    return HttpResponse("Webhook URL is configured correctly", status=200)

JWT_SECRET = getattr(settings, 'JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_DELTA = datetime.timedelta(days=7)

appointment_service = AppointmentService()

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

class ReviewAPIView(APIView):
    """
    API endpoint for patients to submit and view reviews
    """
    def get(self, request, format=None):
        """Get reviews for a doctor or by a patient"""
        doctor_id = request.query_params.get('doctor_id')
        patient_id = request.query_params.get('patient_id')
        appointment_id = request.query_params.get('appointment_id')
        
        if doctor_id:
            # Get reviews for a specific doctor
            reviews = Review.objects.filter(doctor_id=doctor_id)
            
            # Add average rating to response
            try:
                doctor = Doctor.objects.get(id=doctor_id)
                average_rating = doctor.average_rating
                total_reviews = doctor.total_reviews
            except Doctor.DoesNotExist:
                average_rating = None
                total_reviews = 0
                
        elif patient_id:
            # Get reviews submitted by a specific patient
            reviews = Review.objects.filter(patient_id=patient_id)
            average_rating = None
            total_reviews = reviews.count()
        elif appointment_id:
            # Get review for a specific appointment
            try:
                reviews = [Review.objects.get(appointment__appointment_id=appointment_id)]
                average_rating = None
                total_reviews = 1
            except Review.DoesNotExist:
                reviews = []
                average_rating = None
                total_reviews = 0
        else:
            return Response({
                'status': 'error',
                'message': 'Either doctor_id, patient_id, or appointment_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        serializer = ReviewSerializer(reviews, many=True)
        return Response({
            'status': 'success',
            'average_rating': average_rating,
            'total_reviews': total_reviews,
            'reviews': serializer.data
        })
        
    def post(self, request, format=None):
        """Submit a new review"""
        # Get patient ID from token
        patient_id = self._get_patient_id_from_token(request)
        
        if not patient_id:
            return Response({
                'status': 'error',
                'message': 'Invalid or missing authentication token'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        # Add patient_id to request data
        data = request.data.copy()
        data['patient_id'] = patient_id
        
        # Validate the appointment belongs to this patient
        appointment_id = data.get('appointment')
        try:
            # Try to get by appointment_id (hex) first
            if 'appointment_id' in data:
                appointment = Appointment.objects.get(appointment_id=data['appointment_id'])
                # Set the numeric ID for the serializer
                data['appointment'] = appointment.id
            else:
                # Get by numeric ID
                appointment = Appointment.objects.get(id=appointment_id)
                
            if appointment.patient_id != int(patient_id):
                return Response({
                    'status': 'error',
                    'message': 'You can only review your own appointments'
                }, status=status.HTTP_403_FORBIDDEN)
                
            # Check if the appointment is completed
            if appointment.status != 'completed':
                return Response({
                    'status': 'error',
                    'message': 'You can only review completed appointments'
                }, status=status.HTTP_400_BAD_REQUEST)
                
            # Automatically set the doctor_id from the appointment
            data['doctor'] = appointment.doctor.id
            
            # Check if a review already exists for this appointment
            if Review.objects.filter(appointment=appointment).exists():
                return Response({
                    'status': 'error',
                    'message': 'A review already exists for this appointment'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Appointment.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Appointment not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        # Create the review
        serializer = ReviewSerializer(data=data)
        if serializer.is_valid():
            review = serializer.save()
            return Response({
                'status': 'success',
                'message': 'Review submitted successfully',
                'review': ReviewSerializer(review).data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'status': 'error',
                'message': 'Invalid review data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def _get_patient_id_from_token(self, request):
        """Extract patient ID from the authorization token"""
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return None
            
        token = auth_header.split(' ')[1]
        
        try:
            # Decode the JWT token
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload.get('patient_id')
        except Exception as e:
            print(f"Error decoding token: {str(e)}")
            return None

class AppointmentCancelView(APIView):
    """
    API endpoint for canceling an appointment
    """
    permission_classes = [permissions.AllowAny]  # Adjust permissions as needed
    
    def post(self, request, format=None):
        """Cancel an appointment"""
        # Get appointment_id and reason from request
        appointment_id = request.data.get('appointment_id')
        reason = request.data.get('reason', 'Cancelled by patient')
        patient_id = request.data.get('patient_id')
        
        if not appointment_id:
            return Response({
                'status': 'error',
                'message': 'Appointment ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Find the appointment
            appointment = Appointment.objects.get(appointment_id=appointment_id)
            
            # Check if the appointment belongs to the patient (if patient_id provided)
            if patient_id and appointment.patient_id != int(patient_id):
                return Response({
                    'status': 'error',
                    'message': 'Unauthorized to cancel this appointment'
                }, status=status.HTTP_403_FORBIDDEN)
                
            # Check if the appointment can be cancelled (not completed or already cancelled)
            if appointment.status in ['completed', 'cancelled']:
                return Response({
                    'status': 'error',
                    'message': f'Cannot cancel an appointment that is already {appointment.status}'
                }, status=status.HTTP_400_BAD_REQUEST)
                
            # Update the appointment status
            appointment.status = 'cancelled'
            appointment.admin_notes = f"Cancelled by patient. Reason: {reason}"
            appointment.save()
            
            return Response({
                'status': 'success',
                'message': 'Appointment cancelled successfully',
                'appointment_id': appointment_id
            })
            
        except Appointment.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Appointment not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            print(f"Error cancelling appointment: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Error cancelling appointment: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AppointmentSlotAPIView(APIView):
    """
    API view to get available appointment slots for a doctor
    """
    permission_classes = [permissions.AllowAny]  # Allow any user to see slots
    
    def get(self, request, doctor_id, date, format=None):
        try:
            # Convert date string to date object
            appointment_date = datetime.datetime.strptime(date, '%Y-%m-%d').date()
            
            # Get the doctor
            doctor = Doctor.objects.get(id=doctor_id)
            
            # Get day of week
            day_of_week = appointment_date.strftime('%A')
            
            # Check if doctor is available on this day
            try:
                availability = DoctorAvailability.objects.get(
                    doctor=doctor, 
                    day_of_week=day_of_week
                )
                
                if not availability.is_available:
                    return Response({
                        'status': 'error',
                        'message': f'Doctor is not available on {day_of_week}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                    
                # Get doctor's availability settings
                settings = DoctorAvailabilitySettings.objects.get(doctor=doctor)
                
                # Calculate time slots based on doctor's availability and appointment duration
                start_time = availability.start_time
                end_time = availability.end_time
                duration = settings.appointment_duration
                buffer = settings.buffer_time
                
                # Get existing appointments for this day
                existing_appointments = Appointment.objects.filter(
                    doctor=doctor,
                    appointment_date=appointment_date,
                    status__in=['pending', 'confirmed']
                )
                
                # Generate all possible time slots
                slots = []
                current_time = start_time
                
                # Calculate total minutes in the day
                start_minutes = start_time.hour * 60 + start_time.minute
                end_minutes = end_time.hour * 60 + end_time.minute
                total_minutes = end_minutes - start_minutes
                
                slot_duration = duration + buffer
                num_slots = total_minutes // slot_duration
                
                for i in range(num_slots):
                    slot_start = datetime.time(
                        current_time.hour, 
                        current_time.minute
                    )
                    
                    # Calculate slot end time
                    minutes = current_time.hour * 60 + current_time.minute + duration
                    slot_end_hour = minutes // 60
                    slot_end_minute = minutes % 60
                    
                    # Handle time overflow
                    if slot_end_hour >= 24:
                        slot_end_hour = 23
                        slot_end_minute = 59
                        
                    slot_end = datetime.time(slot_end_hour, slot_end_minute)
                    
                    # Check if slot conflicts with any existing appointment
                    is_available = True
                    for appt in existing_appointments:
                        if (
                            (slot_start >= appt.start_time and slot_start < appt.end_time) or
                            (slot_end > appt.start_time and slot_end <= appt.end_time) or
                            (slot_start <= appt.start_time and slot_end >= appt.end_time)
                        ):
                            is_available = False
                            break
                            
                    slots.append({
                        'start_time': slot_start.strftime('%H:%M'),
                        'end_time': slot_end.strftime('%H:%M'),
                        'is_available': is_available
                    })
                    
                    # Move to next slot
                    minutes = current_time.hour * 60 + current_time.minute + slot_duration
                    
                    # Handle time overflow
                    if minutes >= 24 * 60:
                        break
                        
                    current_time = datetime.time(minutes // 60, minutes % 60)
                    
                    # Stop if we've gone past the end time
                    if current_time > end_time:
                        break
                    
                return Response({
                    'status': 'success',
                    'date': date,
                    'day': day_of_week,
                    'slots': slots
                })
                
            except DoctorAvailability.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': f'No availability settings found for {day_of_week}'
                }, status=status.HTTP_404_NOT_FOUND)
                
        except Doctor.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Doctor not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PatientAppointmentAPIView(APIView):
    """
    API endpoint for patients to manage their appointments
    """
    # In views.py, modify the PatientAppointmentAPIView get method
    def get(self, request, format=None):
        """Get all appointments for a patient"""
        # Get patient ID from authorization token
        patient_id = self._get_patient_id_from_token(request)
        
        if not patient_id:
            return Response({
                'status': 'error',
                'message': 'Invalid or missing authentication token'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        # Find all appointments for this patient
        appointments = Appointment.objects.filter(patient_id=patient_id)
        
        # Serialize and return - ADD THE CONTEXT HERE
        serializer = AppointmentSerializer(appointments, many=True, context={'request': request})
        return Response({
            'status': 'success',
            'appointments': serializer.data
        })
               
    def post(self, request, format=None):
        """Create a new appointment for a patient with Zoom integration"""
        # Get patient ID and info from token
        patient_id = self._get_patient_id_from_token(request)
        patient_info = self._get_patient_info_from_token(request)
        
        if not patient_id or not patient_info:
            return Response({
                'status': 'error',
                'message': 'Invalid or missing authentication token'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        # Add patient info to request data
        data = request.data.copy()
        data.update({
            'patient_id': patient_id,
            'patient_name': patient_info.get('name', ''),
            'patient_email': patient_info.get('email', ''),
            'patient_phone': patient_info.get('phone', '')
        })
        
        # Validate appointment data
        serializer = AppointmentCreateSerializer(data=data)
        if serializer.is_valid():
            try:
                # Use the appointment service to create appointment with Zoom meeting
                appointment = appointment_service.create_appointment(serializer.validated_data)
                
                return Response({
                    'status': 'success',
                    'message': 'Appointment created successfully',
                    'appointment': AppointmentSerializer(appointment).data,
                    'zoom_meeting': {
                        'join_url': appointment.zoom_meeting_url,
                        'password': appointment.zoom_meeting_password,
                        'meeting_id': appointment.zoom_meeting_id
                    }
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': f'Error creating appointment: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({
                'status': 'error',
                'message': 'Invalid appointment data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
               
    def _get_patient_id_from_token(self, request):
        """Extract patient ID from the authorization token"""
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return None
            
        token = auth_header.split(' ')[1]
        
        try:
            # Decode the JWT token
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload.get('patient_id')
        except Exception as e:
            print(f"Error decoding token: {str(e)}")
            return None
    
    def _get_patient_info_from_token(self, request):
        """Extract patient information from the authorization token"""
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return None
            
        token = auth_header.split(' ')[1]
        
        try:
            # Decode the JWT token
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return {
                'name': payload.get('name', ''),
                'email': payload.get('email', ''),
                'phone': payload.get('phone', '')
            }
        except Exception as e:
            print(f"Error decoding token: {str(e)}")
            return None

class CrossApplicationAuthAPIView(APIView):
    """
    API view to authenticate users from the Flutter app (doctomoris)
    and issue a special token they can use to access the mediconnect API
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, format=None):
        """Authenticate a user from the doctomoris app"""
        # Get authentication credentials
        doctomoris_token = request.data.get('token')
        patient_id = request.data.get('patient_id')
        patient_name = request.data.get('name')
        patient_email = request.data.get('email')
        patient_phone = request.data.get('phone')
        
        if not doctomoris_token or not patient_id or not patient_email:
            return Response({
                'status': 'error',
                'message': 'Missing required authentication data'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # In a production environment, you would validate the token with doctomoris
            # For now, we'll trust the data sent
            
            # Generate a new token for mediconnect
            mediconnect_token = self._generate_patient_token({
                'patient_id': patient_id,
                'name': patient_name,
                'email': patient_email,
                'phone': patient_phone
            })
            
            return Response({
                'status': 'success',
                'token': mediconnect_token,
                'expires_in': 3600  # Token expiry in seconds (1 hour)
            })
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Authentication failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _generate_patient_token(self, patient_info):
        """
        Generate a token that patients can use to authenticate with mediconnect APIs
        """
        # Create a payload with patient information
        payload = {
            'patient_id': patient_info['patient_id'],
            'name': patient_info['name'],
            'email': patient_info['email'],
            'phone': patient_info.get('phone', ''),
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # 1 hour expiry
        }
        
        # Sign the payload with a secret key
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        return token

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
                'profile_photo': profile_photo_url,
                'average_rating': doctor.average_rating,
                'total_reviews': doctor.total_reviews
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
                'profile_photo': profile_photo_url,
                'average_rating': doctor.average_rating,
                'total_reviews': doctor.total_reviews
            }, status=status.HTTP_200_OK)
            
        except Doctor.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Doctor not found'
            }, status=status.HTTP_404_NOT_FOUND)

class DoctorAvailabilityAPIView(APIView):
    """
    API view to get and update doctor availability
    """
    
    def get(self, request, format=None):
        """
        Get doctor's availability schedule - creates default if none exists
        """
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
            
            # Get availability data
            availabilities = DoctorAvailability.objects.filter(doctor=doctor)
            
            # If no availabilities exist, create default schedule (9-5, Mon-Fri)
            if not availabilities.exists():
                print(f"Creating default schedule for doctor {doctor_id}")
                self._create_default_schedule(doctor)
                # Fetch the newly created schedule
                availabilities = DoctorAvailability.objects.filter(doctor=doctor)
            
            # Get or create settings
            settings, created = DoctorAvailabilitySettings.objects.get_or_create(
                doctor=doctor,
                defaults={
                    'appointment_duration': 30,
                    'buffer_time': 0,
                    'booking_window': 2
                }
            )
            
            # Format data for frontend
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            # Create a lookup dictionary for existing availabilities
            availability_dict = {}
            for avail in availabilities:
                availability_dict[avail.day_of_week] = {
                    'is_available': avail.is_available,
                    'start_time': avail.start_time.strftime('%H:%M'),
                    'end_time': avail.end_time.strftime('%H:%M')
                }
            
            # Build the weekly schedule with all days
            weekly_schedule = []
            for day in days:
                if day in availability_dict:
                    avail = availability_dict[day]
                    weekly_schedule.append({
                        'day': day,
                        'available': avail['is_available'],
                        'startTime': avail['start_time'],
                        'endTime': avail['end_time']
                    })
                else:
                    # Default values for any missing days
                    is_available = day not in ['Saturday', 'Sunday']
                    weekly_schedule.append({
                        'day': day,
                        'available': is_available,
                        'startTime': '09:00',
                        'endTime': '17:00'
                    })
            
            # Return formatted data
            return Response({
                'status': 'success',
                'weeklySchedule': weekly_schedule,
                'settings': {
                    'appointmentDuration': settings.appointment_duration,
                    'bufferTime': settings.buffer_time,
                    'bookingWindow': settings.booking_window
                }
            })
            
        except Doctor.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Doctor not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # Log the full error for debugging
            print(f"Error in GET availability view: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'status': 'error',
                'message': f'Server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _create_default_schedule(self, doctor):
        """Create default 9-5 schedule for Mon-Fri, unavailable on weekends"""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        from datetime import time
        
        for day in days:
            is_available = day not in ['Saturday', 'Sunday']
            DoctorAvailability.objects.create(
                doctor=doctor,
                day_of_week=day,
                is_available=is_available,
                start_time=time(9, 0),  # 9:00 AM
                end_time=time(17, 0)    # 5:00 PM
            )
        
        # Also create default settings
        DoctorAvailabilitySettings.objects.get_or_create(
            doctor=doctor,
            defaults={
                'appointment_duration': 30,
                'buffer_time': 0,
                'booking_window': 2
            }
        )
    
    def post(self, request, format=None):
        """
        Save doctor's availability schedule
        """
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
            
            # Log the received data for debugging
            print("Received data type:", type(request.data))
            if isinstance(request.data, dict):
                print("Received data keys:", request.data.keys())
            else:
                print("Received data:", request.data)
            
            # Handle both dict and JSONParser data
            data = request.data
            if not isinstance(data, dict):
                try:
                    data = json.loads(data)
                except (TypeError, ValueError) as e:
                    print(f"Error parsing JSON data: {str(e)}")
                    return Response({
                        'status': 'error',
                        'message': 'Invalid JSON data format',
                        'detail': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if request data has the expected structure
            if 'weeklySchedule' not in data or 'settings' not in data:
                print("Missing required fields: weeklySchedule or settings")
                return Response({
                    'status': 'error',
                    'message': 'Invalid data format: Missing weeklySchedule or settings',
                    'received_data': data
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate the data structure
            serializer = DoctorAvailabilityUpdateSerializer(data=data)
            
            if not serializer.is_valid():
                print("Serializer validation errors:", serializer.errors)
                return Response({
                    'status': 'error',
                    'message': 'Invalid data format',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Process weekly schedule with database transaction to ensure all or nothing
            with transaction.atomic():
                # Process weekly schedule
                weekly_schedule = serializer.validated_data['weeklySchedule']
                for day_data in weekly_schedule:
                    day = day_data.get('day')
                    is_available = day_data.get('available', False)
                    
                    # Convert string boolean to actual boolean if needed
                    if isinstance(is_available, str):
                        is_available = is_available.lower() == 'true'
                    
                    # Use safe defaults if times aren't provided
                    start_time = day_data.get('startTime', '09:00')
                    end_time = day_data.get('endTime', '17:00')
                    
                    # Convert string times to time objects
                    start_time_obj = self._parse_time(start_time)
                    end_time_obj = self._parse_time(end_time)
                    
                    # Update or create availability record
                    DoctorAvailability.objects.update_or_create(
                        doctor=doctor,
                        day_of_week=day,
                        defaults={
                            'is_available': is_available,
                            'start_time': start_time_obj,
                            'end_time': end_time_obj
                        }
                    )
                
                # Process settings
                settings_data = serializer.validated_data['settings']
                appointment_duration = int(settings_data.get('appointmentDuration', 30))
                buffer_time = int(settings_data.get('bufferTime', 0))
                booking_window = int(settings_data.get('bookingWindow', 2))
                
                DoctorAvailabilitySettings.objects.update_or_create(
                    doctor=doctor,
                    defaults={
                        'appointment_duration': appointment_duration,
                        'buffer_time': buffer_time,
                        'booking_window': booking_window
                    }
                )
            
            return Response({
                'status': 'success',
                'message': 'Availability schedule saved successfully'
            })
            
        except Doctor.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Doctor not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # Log the full error for debugging
            print(f"Error saving availability: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'status': 'error',
                'message': f'An error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _parse_time(self, time_str):
        """Parse time string to time object, handling different formats"""
        from datetime import datetime as dt, time
        
        # Handle different time formats
        try:
            if ':' in time_str:
                parts = time_str.split(':')
                if len(parts) == 2:  # HH:MM
                    hour = int(parts[0])
                    minute = int(parts[1])
                    return time(hour, minute)
                elif len(parts) == 3:  # HH:MM:SS
                    hour = int(parts[0])
                    minute = int(parts[1])
                    return time(hour, minute)
            
            # Default
            return time(9, 0)
        except (ValueError, TypeError):
            # Return default time if parsing fails
            return time(9, 0)
class ZoomMeetingStatusAPIView(APIView):
    """
    API endpoint to get Zoom meeting status for an appointment
    """
    def get(self, request, format=None):
        """Get meeting status for an appointment"""
        # Get appointment ID from query params
        appointment_id = request.query_params.get('appointment_id')
        
        if not appointment_id:
            return Response({
                'status': 'error',
                'message': 'Appointment ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Find the appointment
            appointment = Appointment.objects.get(appointment_id=appointment_id)
            
            # Check if the appointment has a Zoom meeting
            if not appointment.zoom_meeting_id:
                return Response({
                    'status': 'error',
                    'message': 'No Zoom meeting associated with this appointment'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Format the response
            meeting_status = {
                'meeting_id': appointment.zoom_meeting_id,
                'meeting_url': appointment.zoom_meeting_url,
                'status': appointment.zoom_meeting_status,
                'host_joined': appointment.zoom_host_joined,
                'client_joined': appointment.zoom_client_joined,
                'duration': appointment.zoom_meeting_duration
            }
            
            return Response({
                'status': 'success',
                'meeting': meeting_status
            })
            
        except Appointment.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Appointment not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Error getting meeting status: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
class ZoomMeetingStatusAPIView(APIView):
    """
    API endpoint to get Zoom meeting status for an appointment
    """
    def get(self, request, format=None):
        """Get meeting status for an appointment"""
        # Get appointment ID from query params
        appointment_id = request.query_params.get('appointment_id')
        
        if not appointment_id:
            return Response({
                'status': 'error',
                'message': 'Appointment ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Find the appointment
            appointment = Appointment.objects.get(appointment_id=appointment_id)
            
            # Check if the appointment has a Zoom meeting
            if not appointment.zoom_meeting_id:
                return Response({
                    'status': 'error',
                    'message': 'No Zoom meeting associated with this appointment'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Format the response
            meeting_status = {
                'meeting_id': appointment.zoom_meeting_id,
                'meeting_url': appointment.zoom_meeting_url,
                'status': appointment.zoom_meeting_status,
                'host_joined': appointment.zoom_host_joined,
                'client_joined': appointment.zoom_client_joined,
                'duration': appointment.zoom_meeting_duration
            }
            
            return Response({
                'status': 'success',
                'meeting': meeting_status
            })
            
        except Appointment.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Appointment not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Error getting meeting status: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
class ApprovedDoctorsAPIView(APIView):
    """
    API view to list all approved doctors
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, format=None):
        doctors = Doctor.objects.filter(status='approved')
        
        # Format the response with only needed fields
        formatted_doctors = []
        for doctor in doctors:
            # Get profile photo if available
            profile_photo_url = None
            try:
                profile_photo = DoctorDocument.objects.get(
                    doctor=doctor, 
                    document_type='profile_photo'
                )
                profile_photo_url = request.build_absolute_uri(profile_photo.file.url)
            except DoctorDocument.DoesNotExist:
                pass
                
            formatted_doctors.append({
                'id': doctor.id,
                'name': doctor.full_name,
                'specialty': doctor.specialty,
                'about_me': doctor.about_me,
                'profile_photo': profile_photo_url,
                'years_experience': doctor.years_experience,
                'location': f"{doctor.city}, {doctor.country}",
                'average_rating': doctor.average_rating,
                'total_reviews': doctor.total_reviews
            })
            
        return Response({
            'status': 'success',
            'doctors': formatted_doctors
        }, status=status.HTTP_200_OK)

class DoctorWeeklyScheduleAPIView(APIView):
    """
    API view to get a doctor's weekly schedule without authentication
    """
    permission_classes = [permissions.AllowAny]  # Allow any user to see the schedule
    
    def get(self, request, doctor_id, format=None):
        try:
            # Find doctor by ID
            doctor = get_object_or_404(Doctor, id=doctor_id)
            
            # Get availability data
            availabilities = DoctorAvailability.objects.filter(doctor=doctor)
            
            # If no availabilities exist, return empty response
            if not availabilities.exists():
                return Response({
                    'status': 'error',
                    'message': 'No availability schedule found for this doctor'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get settings
            try:
                settings = DoctorAvailabilitySettings.objects.get(doctor=doctor)
            except DoctorAvailabilitySettings.DoesNotExist:
                settings = None
            
            # Format data for frontend
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            # Create a lookup dictionary for existing availabilities
            availability_dict = {}
            for avail in availabilities:
                availability_dict[avail.day_of_week] = {
                    'is_available': avail.is_available,
                    'start_time': avail.start_time.strftime('%H:%M'),
                    'end_time': avail.end_time.strftime('%H:%M')
                }
            
            # Build the weekly schedule with all days
            weekly_schedule = []
            for day in days:
                if day in availability_dict:
                    avail = availability_dict[day]
                    weekly_schedule.append({
                        'day': day,
                        'available': avail['is_available'],
                        'startTime': avail['start_time'],
                        'endTime': avail['end_time']
                    })
                else:
                    # Default values for any missing days
                    is_available = day not in ['Saturday', 'Sunday']
                    weekly_schedule.append({
                        'day': day,
                        'available': is_available,
                        'startTime': '09:00',
                        'endTime': '17:00'
                    })
            
            # Return formatted data
            response_data = {
                'status': 'success',
                'doctor_name': doctor.full_name,
                'doctor_specialty': doctor.specialty,
                'weeklySchedule': weekly_schedule,
            }
            
            # Add settings if available
            if settings:
                response_data['settings'] = {
                    'appointmentDuration': settings.appointment_duration,
                    'bufferTime': settings.buffer_time,
                    'bookingWindow': settings.booking_window
                }
            
            return Response(response_data)
                
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Modify the existing DoctorDashboardStatsAPIView to properly calculate revenue
class DoctorDashboardStatsAPIView(APIView):
    def get(self, request, format=None):
        # Get doctor ID from token
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
            # Get current date
            today = timezone.now().date()
            
            # Total appointments for this doctor
            total_appointments = Appointment.objects.filter(doctor_id=doctor_id).count()
            
            # Upcoming appointments (today or future, not cancelled/completed)
            upcoming_appointments = Appointment.objects.filter(
                doctor_id=doctor_id,
                appointment_date__gte=today,
                status__in=['pending', 'confirmed']
            ).count()
            
            # Calculate total revenue from all completed or confirmed appointments
            revenue_data = Appointment.objects.filter(
                doctor_id=doctor_id,
                status__in=['completed', 'confirmed']
            ).aggregate(
                total_revenue=Sum('amount')
            )
            
            # Handle case where no revenue exists
            total_revenue = revenue_data['total_revenue'] or 0
            
            # Get doctor's rating information
            doctor = Doctor.objects.get(id=doctor_id)
            average_rating = doctor.average_rating
            total_reviews = doctor.total_reviews
            
            return Response({
                'status': 'success',
                'stats': {
                    'total_appointments': total_appointments,
                    'upcoming_appointments': upcoming_appointments,
                    'total_revenue': float(total_revenue),
                    'average_rating': average_rating,
                    'total_reviews': total_reviews
                }
            })
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class DoctorRevenueChartAPIView(APIView):
    """
    API endpoint to get revenue chart data for a doctor
    """
    def get(self, request, format=None):
        # Get doctor ID from token
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
            # Get query parameters
            chart_type = request.query_params.get('type', 'monthly')
            year = int(request.query_params.get('year', timezone.now().year))
            
            if chart_type == 'monthly':
                # Monthly revenue for current year
                monthly_revenue = Appointment.objects.filter(
                    doctor_id=doctor_id,
                    status__in=['completed', 'confirmed'],
                    appointment_date__year=year
                ).annotate(
                    month=TruncMonth('appointment_date')
                ).values('month').annotate(
                    revenue=Sum('amount')
                ).order_by('month')
                
                # Format the data for chart.js
                months = []
                revenues = []
                
                # Create a dictionary with all months initialized to 0
                all_months = {month: 0 for month in range(1, 13)}
                
                # Fill in the actual data
                for item in monthly_revenue:
                    month_num = item['month'].month
                    all_months[month_num] = float(item['revenue'] or 0)
                
                # Convert to sorted lists for the response
                for month_num, revenue in sorted(all_months.items()):
                    # Get month name
                    month_name = datetime.date(2000, month_num, 1).strftime('%b')
                    months.append(month_name)
                    revenues.append(revenue)
                
                return Response({
                    'status': 'success',
                    'chart_data': {
                        'labels': months,
                        'datasets': [
                            {
                                'label': f'Revenue for {year}',
                                'data': revenues
                            }
                        ]
                    }
                })
                
            elif chart_type == 'category':
                # Revenue by appointment type
                category_revenue = Appointment.objects.filter(
                    doctor_id=doctor_id,
                    status__in=['completed', 'confirmed'],
                    appointment_date__year=year
                ).values('package_type').annotate(
                    revenue=Sum('amount')
                ).order_by('package_type')
                
                # Format the data for chart.js
                categories = []
                revenues = []
                
                for item in category_revenue:
                    # Convert from snake_case to Title Case for display
                    category_name = item['package_type'].replace('_', ' ').title()
                    categories.append(category_name)
                    revenues.append(float(item['revenue'] or 0))
                
                return Response({
                    'status': 'success',
                    'chart_data': {
                        'labels': categories,
                        'datasets': [
                            {
                                'label': f'Revenue by Category ({year})',
                                'data': revenues
                            }
                        ]
                    }
                })
                
            else:
                return Response({
                    'status': 'error',
                    'message': 'Invalid chart type'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DoctorRecentAppointmentsAPIView(APIView):
    """
    API endpoint to get all appointments for a doctor with proper pagination support
    """
    def get(self, request, format=None):
        # Get doctor ID from token
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
            # Get limit parameter with a much higher default (1000 to ensure we get all appointments)
            limit = int(request.query_params.get('limit', 1000))
            
            # Log total appointments in database for debugging
            total_in_db = Appointment.objects.filter(doctor_id=doctor_id).count()
            print(f"Total appointments in DB for doctor {doctor_id}: {total_in_db}")
            print(f"Requesting up to {limit} appointments")
            
            # Get all appointments for this doctor, regardless of date or status
            # We'll let the frontend handle filtering and pagination
            all_appointments = Appointment.objects.filter(
                doctor_id=doctor_id
            ).order_by('-appointment_date', '-start_time')[:limit]
            
            # Serialize the appointments
            serializer = AppointmentSerializer(all_appointments, many=True)
            
            print(f"Returning {len(serializer.data)} appointments")
            
            return Response({
                'status': 'success',
                'total_count': total_in_db,
                'appointments': serializer.data
            })
            
        except Exception as e:
            print(f"Error in DoctorRecentAppointmentsAPIView: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AppointmentRescheduleView(APIView):
    """
    API endpoint for rescheduling appointments
    """
    permission_classes = [permissions.AllowAny]  # Adjust permissions as needed
    
    def post(self, request, format=None):
        """Reschedule an appointment"""
        # Get appointment details from request
        appointment_id = request.data.get('appointment_id')
        appointment_date = request.data.get('appointment_date')
        start_time = request.data.get('start_time')
        end_time = request.data.get('end_time')
        new_status = request.data.get('status', 'confirmed')  # Default to confirmed after rescheduling
        
        # Validate required fields
        if not appointment_id or not appointment_date or not start_time or not end_time:
            return Response({
                'status': 'error',
                'message': 'Missing required fields: appointment_id, appointment_date, start_time, end_time'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Find the appointment
            appointment = None
            
            # Try to find by hex ID first (most common case)
            try:
                appointment = Appointment.objects.get(appointment_id=appointment_id)
            except Appointment.DoesNotExist:
                # Try to find by numeric ID
                try:
                    appointment = Appointment.objects.get(id=int(appointment_id))
                except (Appointment.DoesNotExist, ValueError):
                    return Response({
                        'status': 'error',
                        'message': 'Appointment not found'
                    }, status=status.HTTP_404_NOT_FOUND)
            
            # Validate the appointment can be rescheduled
            if appointment.status in ['completed']:
                return Response({
                    'status': 'error',
                    'message': f'Cannot reschedule an appointment that is already {appointment.status}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse date string to date object
            from datetime import datetime
            try:
                # Parse date from ISO format (YYYY-MM-DD)
                if isinstance(appointment_date, str):
                    parsed_date = datetime.strptime(appointment_date, '%Y-%m-%d').date()
                else:
                    parsed_date = appointment_date
                    
                # Parse times from string format
                if isinstance(start_time, str):
                    if ':' in start_time:
                        if 'AM' in start_time.upper() or 'PM' in start_time.upper():
                            # Parse 12-hour format (e.g., "9:00 AM")
                            parsed_start_time = datetime.strptime(start_time, '%I:%M %p').time()
                        else:
                            # Parse 24-hour format (e.g., "09:00")
                            parsed_start_time = datetime.strptime(start_time, '%H:%M').time()
                    else:
                        return Response({
                            'status': 'error',
                            'message': f'Invalid start time format: {start_time}'
                        }, status=status.HTTP_400_BAD_REQUEST)
                else:
                    parsed_start_time = start_time
                    
                if isinstance(end_time, str):
                    if ':' in end_time:
                        if 'AM' in end_time.upper() or 'PM' in end_time.upper():
                            # Parse 12-hour format (e.g., "9:30 AM")
                            parsed_end_time = datetime.strptime(end_time, '%I:%M %p').time()
                        else:
                            # Parse 24-hour format (e.g., "09:30")
                            parsed_end_time = datetime.strptime(end_time, '%H:%M').time()
                    else:
                        return Response({
                            'status': 'error',
                            'message': f'Invalid end time format: {end_time}'
                        }, status=status.HTTP_400_BAD_REQUEST)
                else:
                    parsed_end_time = end_time
                    
            except ValueError as e:
                return Response({
                    'status': 'error',
                    'message': f'Error parsing date or time: {str(e)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if the new time slot conflicts with existing appointments
            doctor = appointment.doctor
            conflicting_appointments = Appointment.objects.filter(
                doctor=doctor,
                appointment_date=parsed_date,
                status__in=['pending', 'confirmed']
            ).exclude(
                id=appointment.id  # Exclude the current appointment
            ).filter(
                # Time slot overlaps with another appointment
                models.Q(start_time__lt=parsed_end_time, end_time__gt=parsed_start_time)
            )
            
            if conflicting_appointments.exists():
                conflicting_appointment = conflicting_appointments.first()
                return Response({
                    'status': 'error',
                    'message': 'The selected time slot conflicts with another appointment',
                    'conflict': {
                        'appointment_id': conflicting_appointment.appointment_id,
                        'start_time': conflicting_appointment.start_time.strftime('%H:%M'),
                        'end_time': conflicting_appointment.end_time.strftime('%H:%M')
                    }
                }, status=status.HTTP_409_CONFLICT)
            
            # Check doctor availability for this day
            day_of_week = parsed_date.strftime('%A')
            try:
                availability = DoctorAvailability.objects.get(
                    doctor=doctor,
                    day_of_week=day_of_week
                )
                
                if not availability.is_available:
                    return Response({
                        'status': 'error',
                        'message': f'Doctor is not available on {day_of_week}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                    
                if parsed_start_time < availability.start_time or parsed_end_time > availability.end_time:
                    return Response({
                        'status': 'error',
                        'message': f'Selected time is outside doctor\'s availability hours ({availability.start_time} - {availability.end_time})'
                    }, status=status.HTTP_400_BAD_REQUEST)
                    
            except DoctorAvailability.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': f'No availability settings found for {day_of_week}'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Update the appointment
            old_date = appointment.appointment_date
            old_start_time = appointment.start_time
            old_end_time = appointment.end_time
            old_status = appointment.status
            
            appointment.appointment_date = parsed_date
            appointment.start_time = parsed_start_time
            appointment.end_time = parsed_end_time
            appointment.status = new_status
            appointment.save()
            
            # Add a note about the rescheduling
            if appointment.admin_notes:
                appointment.admin_notes += f"\n[{timezone.now().strftime('%Y-%m-%d %H:%M')}] Rescheduled from {old_date} {old_start_time}-{old_end_time} to {parsed_date} {parsed_start_time}-{parsed_end_time}. Previous status: {old_status}."
            else:
                appointment.admin_notes = f"[{timezone.now().strftime('%Y-%m-%d %H:%M')}] Rescheduled from {old_date} {old_start_time}-{old_end_time} to {parsed_date} {parsed_start_time}-{parsed_end_time}. Previous status: {old_status}."
            
            appointment.save(update_fields=['admin_notes'])
            
            return Response({
                'status': 'success',
                'message': 'Appointment rescheduled successfully',
                'appointment': {
                    'id': appointment.id,
                    'appointment_id': appointment.appointment_id,
                    'appointment_date': appointment.appointment_date,
                    'start_time': appointment.start_time.strftime('%H:%M'),
                    'end_time': appointment.end_time.strftime('%H:%M'),
                    'status': appointment.status
                }
            })
            
        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"Error rescheduling appointment: {str(e)}")
            print(trace)
            return Response({
                'status': 'error',
                'message': f'Error rescheduling appointment: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
# Add these to your doctors/views.py file

class SupportTicketAPIView(APIView):
    """
    API endpoint for creating and retrieving support tickets
    """
    parser_classes = (MultiPartParser, FormParser)
    
    def get(self, request, format=None):
        """Get support tickets for a doctor or patient"""
        # Check if authenticated as doctor
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return Response({
                'status': 'error',
                'message': 'Authentication token required'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        token = auth_header.split(' ')[1]
        doctor_id = verify_token(token)
        
        if doctor_id:
            # Doctor is authenticated, return their tickets
            tickets = SupportTicket.objects.filter(doctor_id=doctor_id)
            serializer = SupportTicketSerializer(tickets, many=True)
            return Response({
                'status': 'success',
                'tickets': serializer.data
            })
        else:
            # Check if authenticated as patient
            try:
                # Decode the JWT token
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                patient_id = payload.get('patient_id')
                
                if patient_id:
                    tickets = SupportTicket.objects.filter(patient_id=patient_id)
                    serializer = SupportTicketSerializer(tickets, many=True)
                    return Response({
                        'status': 'success',
                        'tickets': serializer.data
                    })
                else:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid or expired token'
                    }, status=status.HTTP_401_UNAUTHORIZED)
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': 'Invalid or expired token'
                }, status=status.HTTP_401_UNAUTHORIZED)
    
    def post(self, request, format=None):
        """Create a new support ticket"""
        # Check authentication
        doctor_id = None
        patient_id = None
        user_type = 'doctor'  # Default
        
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            # Check if doctor token
            doctor_id = verify_token(token)
            
            if not doctor_id:
                # Check if patient token
                try:
                    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                    patient_id = payload.get('patient_id')
                    if patient_id:
                        user_type = 'patient'
                except Exception:
                    pass
        
        # Create a copy of the request data to modify
        data = request.data.copy()
        
        # Add user_type, doctor_id, or patient_id if authenticated
        if doctor_id:
            data['user_type'] = 'doctor'
            data['doctor'] = doctor_id
        elif patient_id:
            data['user_type'] = 'patient'
            data['patient_id'] = patient_id
        
        # Create ticket
        serializer = SupportTicketCreateSerializer(data=data)
        if serializer.is_valid():
            ticket = serializer.save()
            return Response({
                'status': 'success',
                'message': 'Support ticket created successfully',
                'ticket_id': ticket.ticket_id
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'status': 'error',
                'message': 'Invalid form data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)


class FAQAPIView(APIView):
    """
    API endpoint for retrieving FAQs
    """
    permission_classes = [permissions.AllowAny]  # Public access
    
    def get(self, request, format=None):
        """Get published FAQs, optionally filtered by category"""
        category = request.query_params.get('category')
        
        # Filter by published status and optionally by category
        query = Q(is_published=True)
        if category:
            query &= Q(category=category)
            
        faqs = FAQ.objects.filter(query).order_by('order', 'category')
        
        # Group by category if requested
        grouped = request.query_params.get('grouped', 'false').lower() == 'true'
        
        if grouped:
            # Group FAQs by category
            categories = {}
            for faq in faqs:
                category_name = faq.get_category_display()
                if category_name not in categories:
                    categories[category_name] = []
                    
                categories[category_name].append({
                    'id': faq.id,
                    'question': faq.question,
                    'answer': faq.answer,
                    'order': faq.order
                })
                
            return Response({
                'status': 'success',
                'categories': categories
            })
        else:
            # Return flat list of FAQs
            serializer = FAQSerializer(faqs, many=True)
            return Response({
                'status': 'success',
                'faqs': serializer.data
            })            

# Add this to your doctors/views.py file

class DoctorPatientsAPIView(APIView):
    """
    API endpoint to get all unique patients for a doctor
    """
    def get(self, request, format=None):
        # Get doctor ID from token
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
            # Get all appointments for this doctor
            appointments = Appointment.objects.filter(doctor_id=doctor_id)
            
            # Get unique patient IDs
            patient_ids = list(appointments.values_list('patient_id', flat=True).distinct())
            
            # For each patient, gather their details and latest appointment
            patients_data = []
            for patient_id in patient_ids:
                # Get the latest appointment for this patient
                latest_appointment = Appointment.objects.filter(
                    doctor_id=doctor_id,
                    patient_id=patient_id
                ).order_by('-appointment_date', '-start_time').first()
                
                if not latest_appointment:
                    continue
                
                # Get all appointments for this patient
                all_appointments = Appointment.objects.filter(
                    doctor_id=doctor_id,
                    patient_id=patient_id
                )
                appointment_count = all_appointments.count()
                
                # Determine gender based on naming patterns (very basic approach)
                # In a real app, you'd have this stored in your patient model
                name = latest_appointment.patient_name
                gender = 'Male'  # Default
                
                # Very simple gender detection
                common_female_names = ['mary', 'patricia', 'jennifer', 'linda', 'elizabeth', 
                                     'barbara', 'susan', 'jessica', 'sarah', 'karen', 'nancy', 
                                     'margaret', 'lisa', 'betty', 'dorothy', 'sandra', 'ashley', 
                                     'kimberly', 'donna', 'emily', 'michelle', 'carol', 'amanda', 
                                     'melissa', 'deborah', 'stephanie', 'laura', 'olivia', 'emma']
                
                # Check first name against common female names
                first_name = name.split(' ')[0].lower() if ' ' in name else name.lower()
                if first_name in common_female_names:
                    gender = 'Female'
                
                patients_data.append({
                    'id': patient_id,
                    'patient_id': f"P-{patient_id:06}",  # Format: P-000123
                    'name': latest_appointment.patient_name,
                    'email': latest_appointment.patient_email,
                    'phone': latest_appointment.patient_phone,
                    'gender': gender,
                    'latest_appointment': {
                        'id': latest_appointment.id,
                        'appointment_id': latest_appointment.appointment_id,
                        'date': latest_appointment.appointment_date.strftime('%b %d, %Y'),
                        'time': latest_appointment.start_time.strftime('%I:%M %p'),
                        'reason': latest_appointment.problem_description,
                        'status': latest_appointment.status
                    },
                    'appointment_count': appointment_count
                })
            
            return Response({
                'status': 'success',
                'total_patients': len(patients_data),
                'patients': patients_data
            })
            
        except Exception as e:
            print(f"Error in DoctorPatientsAPIView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=rest_framework.status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def patient_medical_history(request, patient_id):
    """Enhanced endpoint to fetch medical history with better diagnostics"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Received request for patient medical history: patient_id={patient_id}")
    
    try:
        # Get the auth token from the request
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return Response({"status": "error", "message": "Authentication required"}, 
                          status=status.HTTP_401_UNAUTHORIZED)
        
        # Prepare the response data structure
        response_data = {
            "status": "success",
            "medical_history": None,
            "documents": []
        }
        
        # STEP 1: First check if we have data locally in our database
        try:
            from patient_records.models import MedicalHistory
            # Try to get medical history directly from our database
            logger.info(f"Checking for medical history in local database for user_id={patient_id}")
            local_history = MedicalHistory.objects.filter(user_id=patient_id).first()
            
            if local_history:
                logger.info(f"✓ Found medical history in local database for user_id={patient_id}")
                # Use the data from our own database
                response_data["medical_history"] = {
                    "allergies": local_history.allergies,
                    "chronic_diseases": local_history.chronic_diseases,
                    "surgeries": local_history.surgeries,
                    "current_medications": local_history.current_medications,
                    "family_medical_history": local_history.family_medical_history,
                    "additional_notes": local_history.additional_notes
                }
                
                # Also get documents if available
                if hasattr(local_history, 'documents'):
                    documents = local_history.documents.all()
                    logger.info(f"Found {documents.count()} documents for user_id={patient_id}")
                    
                    document_list = []
                    for doc in documents:
                        document_list.append({
                            "id": doc.id,
                            "title": doc.title,
                            "document_type": doc.document_type,
                            "document_url": request.build_absolute_uri(doc.document.url) if doc.document else None,
                            "uploaded_at": doc.uploaded_at
                        })
                    
                    response_data["documents"] = document_list
                
                # If we found local data, we can return it immediately
                logger.info(f"Returning local medical history data for user_id={patient_id}")
                return Response(response_data)
            else:
                logger.info(f"✗ No medical history found in local database for user_id={patient_id}")
        except Exception as local_db_error:
            logger.exception(f"Error checking local database: {str(local_db_error)}")
        
        # STEP 2: If we don't have local data, try the DoctoMoris API
        logger.info(f"Attempting to fetch medical history from DoctoMoris API for patient_id={patient_id}")
        
        # Configure the DoctoMoris API endpoint URL
        DOCTOMORIS_API_BASE = "https://doctomoris.onrender.com/api/"
        
        # Make the request to DoctoMoris API
        headers = {
            'Authorization': auth_header,
            'Content-Type': 'application/json'
        }
        
        # First, try to get medical history
        med_history_url = f"{DOCTOMORIS_API_BASE}/medical-history/{patient_id}/"
        logger.info(f"Making request to DoctoMoris API: {med_history_url}")
        
        med_history_response = requests.get(med_history_url, headers=headers)
        logger.info(f"DoctoMoris medical history response status: {med_history_response.status_code}")
        
        # Then try to get documents
        documents_url = f"{DOCTOMORIS_API_BASE}/medical-documents/?patient_id={patient_id}"
        logger.info(f"Making request to DoctoMoris API: {documents_url}")
        
        documents_response = requests.get(documents_url, headers=headers)
        logger.info(f"DoctoMoris documents response status: {documents_response.status_code}")
        
        # Add medical history if available from DoctoMoris
        if med_history_response.status_code == 200:
            try:
                med_history_data = med_history_response.json()
                logger.info(f"Successfully parsed medical history from DoctoMoris: {med_history_data}")
                response_data["medical_history"] = med_history_data
            except Exception as json_error:
                logger.exception(f"Error parsing medical history JSON: {str(json_error)}")
                logger.info(f"Raw response from DoctoMoris: {med_history_response.text[:500]}")  # Log first 500 chars
        else:
            logger.warning(f"Failed to get medical history from DoctoMoris: {med_history_response.status_code}")
            try:
                logger.warning(f"DoctoMoris error details: {med_history_response.text[:500]}")
            except:
                pass
        
        # Add documents if available from DoctoMoris
        if documents_response.status_code == 200:
            try:
                documents_data = documents_response.json()
                logger.info(f"Successfully parsed {len(documents_data)} documents from DoctoMoris")
                response_data["documents"] = documents_data
            except Exception as json_error:
                logger.exception(f"Error parsing documents JSON: {str(json_error)}")
        else:
            logger.warning(f"Failed to get documents from DoctoMoris: {documents_response.status_code}")
        
        # STEP 3: If we still don't have data, add some debug info to the response
        if response_data["medical_history"] is None:
            logger.warning(f"No medical history found for patient_id={patient_id} in either system")
            # Add debug info to the response (will be removed in production)
            if settings.DEBUG:
                response_data["debug_info"] = {
                    "checked_local_db": True,
                    "local_db_result": "Not found",
                    "checked_doctomoris": True,
                    "doctomoris_status": med_history_response.status_code,
                    "patient_id_used": patient_id,
                    "timestamp": datetime.datetime.now().isoformat()
                }
        
        return Response(response_data)
    
    except requests.RequestException as e:
        logger.exception(f"Network error connecting to DoctoMoris API: {str(e)}")
        return Response(
            {"status": "error", "message": f"Error connecting to DoctoMoris API: {str(e)}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except Exception as e:
        logger.exception(f"Unexpected error in patient_medical_history view: {str(e)}")
        return Response(
            {"status": "error", "message": f"Internal server error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
