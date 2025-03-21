# doctors/serializers.py

from rest_framework import serializers
from .models import Doctor, DoctorDocument

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