# doctors/serializers.py

from rest_framework import serializers
from .models import Doctor, DoctorDocument, Review
from .models import DoctorAvailability, DoctorAvailabilitySettings
from .models import Appointment
from django.db import models
from .models import SupportTicket, FAQ 




class DoctorDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorDocument
        fields = ['id', 'document_type', 'file', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']


class DoctorSerializer(serializers.ModelSerializer):
    documents = DoctorDocumentSerializer(many=True, read_only=True)
    
    class Meta:
        model = Doctor
        fields = '__all__'
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']

# In serializers.py, modify the AppointmentSerializer
class AppointmentSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    doctor_photo = serializers.SerializerMethodField()
    
    class Meta:
        model = Appointment
        fields = [
            'id', 'appointment_id', 'doctor', 'doctor_name', 'patient_id', 'patient_name', 
            'patient_email', 'patient_phone', 'appointment_date', 'start_time', 'end_time', 
            'package_type', 'problem_description', 'transaction_number', 'amount', 'status', 
            'created_at', 'updated_at', 'doctor_notes', 'admin_notes',
            'zoom_meeting_id', 'zoom_meeting_url', 'zoom_meeting_password', 'zoom_meeting_status',
            'zoom_host_joined', 'zoom_client_joined', 'zoom_meeting_duration', 'doctor_photo'
        ]
        read_only_fields = ['id', 'appointment_id', 'created_at', 'updated_at']
    
    def get_doctor_photo(self, obj):
        """Get the doctor's profile photo with correct Firebase URL"""
        try:
            # Try to get profile photo
            profile_photo = DoctorDocument.objects.get(
                doctor=obj.doctor, 
                document_type='profile_photo'
            )
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(profile_photo.file.url)
            else:
                # Direct Firebase URL if no request context is available
                return profile_photo.file.url
        except DoctorDocument.DoesNotExist:
            return None
                    
class DoctorSerializer(serializers.ModelSerializer):
    documents = DoctorDocumentSerializer(many=True, read_only=True)
    
    class Meta:
        model = Doctor
        fields = '__all__'
        read_only_fields = ['id', 'status', 'created_at', 'updated_at', 'average_rating', 'total_reviews']

class ReviewSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    patient_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = ['id', 'appointment', 'doctor', 'doctor_name', 'patient_id', 
                 'patient_name', 'rating', 'review_text', 'created_at']
        read_only_fields = ['id', 'created_at', 'doctor_name', 'patient_name']
    
    def get_patient_name(self, obj):
        """Get patient name from the User model"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=obj.patient_id)
            return user.name
        except User.DoesNotExist:
            return f"Patient #{obj.patient_id}"

                
class AppointmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        exclude = ['status', 'doctor_notes', 'admin_notes', 'created_at', 'updated_at']
        read_only_fields = ['appointment_id']  # Mark appointment_id as read-only
        
    def validate(self, data):
        """
        Validate that the appointment doesn't conflict with others
        and is within doctor's availability
        """
        doctor = data['doctor']
        date = data['appointment_date']
        start_time = data['start_time']
        end_time = data['end_time']
        
        # Convert date to weekday name (Monday, Tuesday, etc.)
        day_of_week = date.strftime('%A')
        
        # Check if doctor is available on this day and time
        try:
            availability = DoctorAvailability.objects.get(
                doctor=doctor,
                day_of_week=day_of_week
            )
            
            if not availability.is_available:
                raise serializers.ValidationError(f"Doctor is not available on {day_of_week}")
                
            if start_time < availability.start_time or end_time > availability.end_time:
                raise serializers.ValidationError(
                    f"Appointment time must be between {availability.start_time} and {availability.end_time}"
                )
                
        except DoctorAvailability.DoesNotExist:
            raise serializers.ValidationError(f"No availability settings found for {day_of_week}")
            
        # Check for conflicts with existing appointments
        conflicts = Appointment.objects.filter(
            doctor=doctor,
            appointment_date=date,
            status__in=['pending', 'confirmed'],  # Only check active appointments
        ).filter(
            # Appointment starts during another appointment
            models.Q(start_time__lte=start_time, end_time__gt=start_time) |
            # Appointment ends during another appointment
            models.Q(start_time__lt=end_time, end_time__gte=end_time) |
            # Appointment contains another appointment
            models.Q(start_time__gte=start_time, end_time__lte=end_time)
        )
        
        if conflicts.exists():
            raise serializers.ValidationError("This time slot is already booked")
            
        return data
class DoctorRegistrationSerializer(serializers.ModelSerializer):
    profile_photo = serializers.FileField(write_only=True, required=False)
    medical_license = serializers.FileField(write_only=True, required=False)
    medical_degree = serializers.FileField(write_only=True, required=False)
    additional_documents = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = Doctor
        exclude = ['status', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        # Extract the document files from validated_data
        profile_photo = validated_data.pop('profile_photo', None)
        medical_license = validated_data.pop('medical_license', None)
        medical_degree = validated_data.pop('medical_degree', None)
        additional_documents = validated_data.pop('additional_documents', [])
        
        # Create the Doctor instance
        doctor = Doctor.objects.create(**validated_data)
        
        # Create DoctorDocument instances for each uploaded file
        if profile_photo:
            DoctorDocument.objects.create(
                doctor=doctor,
                document_type='profile_photo',
                file=profile_photo
            )
            
        if medical_license:
            DoctorDocument.objects.create(
                doctor=doctor,
                document_type='medical_license',
                file=medical_license
            )
            
        if medical_degree:
            DoctorDocument.objects.create(
                doctor=doctor,
                document_type='medical_degree',
                file=medical_degree
            )
            
        # Create DoctorDocument instances for additional documents
        for doc in additional_documents:
            DoctorDocument.objects.create(
                doctor=doctor,
                document_type='additional_certificate',
                file=doc
            )
            
        return doctor
    
class DoctorAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorAvailability
        fields = ['id', 'day_of_week', 'is_available', 'start_time', 'end_time']
        
    def validate(self, data):
        """
        Check that start time is before end time.
        """
        if data['start_time'] >= data['end_time']:
            raise serializers.ValidationError("End time must be after start time")
        return data

class DoctorAvailabilitySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorAvailabilitySettings
        fields = ['appointment_duration', 'buffer_time', 'booking_window']

class DoctorAvailabilityUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating a doctor's entire weekly schedule and settings at once.
    Very flexible to handle various input formats and provide defaults.
    """
    weeklySchedule = serializers.ListField(
        child=serializers.DictField(
            # Use CharField that can accept any values including None
            child=serializers.CharField(required=False, allow_null=True, allow_blank=True),
            allow_empty=True
        ),
        required=True
    )
    settings = serializers.DictField(
        child=serializers.CharField(required=False, allow_null=True, allow_blank=True),
        allow_empty=True,
        required=True
    )
    
    def validate_weeklySchedule(self, value):
        """
        Validate each day in the weekly schedule.
        """
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        valid_days = set(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])
        
        logger.debug(f"Validating weeklySchedule: {json.dumps(value)}")
        
        # Ensure it's a list
        if not isinstance(value, list):
            raise serializers.ValidationError("weeklySchedule must be a list")
        
        for i, day_data in enumerate(value):
            logger.debug(f"Validating day {i}: {json.dumps(day_data)}")
            
            # Check for required day field
            if 'day' not in day_data:
                # If day is missing, try to infer it from the index
                if i < len(valid_days):
                    days_list = list(valid_days)
                    day_data['day'] = days_list[i]
                else:
                    raise serializers.ValidationError(f"Item {i} missing 'day' field")
            
            # Validate day value
            if day_data['day'] not in valid_days:
                raise serializers.ValidationError(f"Invalid day: {day_data['day']}")
            
            # Handle available field - support different formats
            if 'available' not in day_data:
                # Default to available for weekdays, not available for weekends
                day_data['available'] = day_data['day'] not in ['Saturday', 'Sunday']
            else:
                # Convert various values to boolean
                if isinstance(day_data['available'], str):
                    day_data['available'] = day_data['available'].lower() in ['true', 'yes', '1', 't', 'y']
                elif day_data['available'] is None:
                    day_data['available'] = False
                else:
                    day_data['available'] = bool(day_data['available'])
            
            # Ensure time fields exist with defaults
            if 'startTime' not in day_data or not day_data['startTime']:
                day_data['startTime'] = '09:00'
                
            if 'endTime' not in day_data or not day_data['endTime']:
                day_data['endTime'] = '17:00'
                
        return value
    
    def validate_settings(self, value):
        """
        Validate the settings data.
        """
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        logger.debug(f"Validating settings: {json.dumps(value)}")
        
        # Create a new dictionary with default values for required fields
        defaults = {
            'appointmentDuration': '30',
            'bufferTime': '0', 
            'bookingWindow': '2'
        }
        
        # Replace missing or invalid values with defaults
        for key, default in defaults.items():
            if key not in value or not value[key]:
                value[key] = default
            else:
                # Try to convert to int to validate
                try:
                    int(value[key])
                except (ValueError, TypeError):
                    value[key] = default
        
        return value
    
    def validate(self, data):
        """
        Final validation of the entire data structure
        """
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        logger.debug(f"Final validation of data: {json.dumps(data)}")
        return data


# Add these to your doctors/serializers.py file

class SupportTicketSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    subject_display = serializers.CharField(source='get_subject_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = SupportTicket
        fields = ['id', 'ticket_id', 'full_name', 'email', 'subject', 'subject_display', 
                 'message', 'status', 'status_display', 'user_type', 'doctor', 
                 'doctor_name', 'patient_id', 'response', 'created_at', 'updated_at', 'resolved_at']
        read_only_fields = ['id', 'ticket_id', 'status', 'response', 'created_at', 'updated_at', 'resolved_at']


class SupportTicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = ['full_name', 'email', 'subject', 'message', 'attachments', 'user_type', 'doctor', 'patient_id']
        

class FAQSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    
    class Meta:
        model = FAQ
        fields = ['id', 'question', 'answer', 'category', 'category_display', 'order', 'is_published']

