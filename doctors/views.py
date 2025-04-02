from django.shortcuts import render, get_object_or_404
from rest_framework import status, permissions 
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Doctor, DoctorDocument, DoctorAccount
from .serializers import DoctorSerializer, DoctorRegistrationSerializer
from django.utils import timezone
from django.contrib.auth.hashers import check_password
from django.conf import settings
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
from django.db.models import Q
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
        
        # Serialize and return
        serializer = AppointmentSerializer(appointments, many=True)
        return Response({
            'status': 'success',
            'appointments': serializer.data
        })
        
    def post(self, request, format=None):
        """Create a new appointment for a patient"""
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
        
        # Create appointment
        serializer = AppointmentCreateSerializer(data=data)
        if serializer.is_valid():
            appointment = serializer.save()
            return Response({
                'status': 'success',
                'message': 'Appointment created successfully',
                'appointment': AppointmentSerializer(appointment).data
            }, status=status.HTTP_201_CREATED)
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
                'location': f"{doctor.city}, {doctor.country}"
                
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
class DoctorDashboardStatsAPIView(APIView):
    """
    API endpoint to get dashboard statistics for a doctor
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
            
            # Total revenue
            revenue_data = Appointment.objects.filter(
                doctor_id=doctor_id,
                status__in=['completed', 'confirmed']  # Only count revenue from completed/confirmed appointments
            ).aggregate(total_revenue=Sum('amount'))
            
            total_revenue = revenue_data['total_revenue'] or 0
            
            return Response({
                'status': 'success',
                'stats': {
                    'total_appointments': total_appointments,
                    'upcoming_appointments': upcoming_appointments,
                    'total_revenue': float(total_revenue)
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
