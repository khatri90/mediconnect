from rest_framework import serializers
from .models import Hospital, Department

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name', 'description', 'head_doctor', 
                  'contact_email', 'contact_phone', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class HospitalSerializer(serializers.ModelSerializer):
    departments = DepartmentSerializer(many=True, read_only=True)
    main_image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Hospital
        fields = ['id', 'name', 'city', 'location', 'about', 'specialties',
                  'email', 'phone', 'website', 'main_image', 'thumbnail',
                  'main_image_url', 'thumbnail_url', 'departments',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'main_image_url', 'thumbnail_url']
        
    def get_main_image_url(self, obj):
        if obj.main_image:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.main_image.url) if request else obj.main_image.url
        return None
        
    def get_thumbnail_url(self, obj):
        if obj.thumbnail:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.thumbnail.url) if request else obj.thumbnail.url
        return None

class HospitalListSerializer(serializers.ModelSerializer):
    thumbnail_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Hospital
        fields = ['id', 'name', 'city', 'specialties', 'phone', 'thumbnail', 'thumbnail_url']
        
    def get_thumbnail_url(self, obj):
        if obj.thumbnail:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.thumbnail.url) if request else obj.thumbnail.url
        return None

class DepartmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['name', 'description', 'head_doctor', 'contact_email', 'contact_phone']

class HospitalWithDepartmentsSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a hospital with departments in a single request
    """
    departments = DepartmentCreateSerializer(many=True, required=False)
    
    class Meta:
        model = Hospital
        fields = ['id', 'name', 'city', 'location', 'about', 'specialties',
                  'email', 'phone', 'website', 'main_image', 'thumbnail',
                  'departments']
    
    def create(self, validated_data):
        departments_data = validated_data.pop('departments', [])
        hospital = Hospital.objects.create(**validated_data)
        
        for department_data in departments_data:
            Department.objects.create(hospital=hospital, **department_data)
        
        return hospital
    
    def update(self, instance, validated_data):
        departments_data = validated_data.pop('departments', [])
        
        # Update hospital fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update departments if provided
        if departments_data:
            # Clear existing departments and create new ones
            instance.departments.all().delete()
            for department_data in departments_data:
                Department.objects.create(hospital=instance, **department_data)
        
        return instance