from rest_framework import serializers
from .models import Patient, PatientAccount, MedicalRecord, PatientDocument
from django.contrib.auth.hashers import make_password

class PatientDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientDocument
        fields = ['id', 'document_type', 'title', 'file', 'notes', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

class MedicalRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalRecord
        fields = ['id', 'doctor_name', 'doctor_id', 'record_date', 'diagnosis', 
                  'treatment', 'prescription', 'notes', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class PatientSerializer(serializers.ModelSerializer):
    documents = PatientDocumentSerializer(many=True, read_only=True)
    medical_records = MedicalRecordSerializer(many=True, read_only=True)
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = Patient
        fields = ['id', 'email', 'name', 'phone_number', 'dob', 'gender', 
                  'allergies', 'medical_conditions', 'medications', 'blood_type',
                  'documents', 'medical_records', 'password']
        read_only_fields = ['id']
        extra_kwargs = {
            'password': {'write_only': True}
        }
    
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        patient = Patient.objects.create_patient(**validated_data)
        
        if password:
            # Create PatientAccount
            PatientAccount.objects.create(
                patient=patient,
                username=patient.email,
                password_hash=make_password(password)
            )
        
        return patient
    
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        
        # Update patient instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update password if provided
        if password:
            try:
                account = PatientAccount.objects.get(patient=instance)
                account.set_password(password)
            except PatientAccount.DoesNotExist:
                PatientAccount.objects.create(
                    patient=instance,
                    username=instance.email,
                    password_hash=make_password(password)
                )
        
        return instance

class PatientProfileSerializer(serializers.ModelSerializer):
    """
    A simplified serializer for returning patient profile information
    """
    class Meta:
        model = Patient
        fields = ['id', 'email', 'name', 'phone_number', 'dob', 'gender', 
                  'allergies', 'medical_conditions', 'medications', 'blood_type']
        read_only_fields = ['id', 'email']

class PatientLoginSerializer(serializers.Serializer):
    """
    Serializer for patient login endpoint
    """
    email = serializers.EmailField()
    password = serializers.CharField(style={'input_type': 'password'})

class PatientRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for patient registration with extra validation
    """
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = Patient
        fields = ['email', 'name', 'phone_number', 'dob', 'gender', 
                  'allergies', 'medical_conditions', 'medications', 'blood_type',
                  'password', 'confirm_password']
    
    def validate(self, attrs):
        password = attrs.get('password')
        confirm_password = attrs.pop('confirm_password', None)
        
        if password != confirm_password:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        
        if len(password) < 8:
            raise serializers.ValidationError({"password": "Password must be at least 8 characters long."})
        
        return attrs
    
    def create(self, validated_data):
        return Patient.objects.create_patient(**validated_data)

class PatientDocumentUploadSerializer(serializers.ModelSerializer):
    """
    Serializer for uploading patient documents
    """
    class Meta:
        model = PatientDocument
        fields = ['document_type', 'title', 'file', 'notes']