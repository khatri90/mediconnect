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
from .views import (
    DoctorRegistrationAPIView
)
import json
import traceback
from django.db.models import Q
from .models import Appointment
from .serializers import AppointmentSerializer, AppointmentCreateSerializer


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
