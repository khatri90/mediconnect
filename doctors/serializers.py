# doctors/serializers.py

from rest_framework import serializers
from .models import Doctor, DoctorDocument
from .models import DoctorAvailability, DoctorAvailabilitySettings

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
