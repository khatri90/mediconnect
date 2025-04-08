from rest_framework import serializers
from django.contrib.auth.models import User
from doctors.models import Doctor, DoctorDocument, FAQ, SupportTicket, Review, Appointment
from doctors.serializers import DoctorSerializer

class AdminUserSerializer(serializers.ModelSerializer):
    """Serializer for Django User model with administrative fields"""
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 
                  'is_active', 'is_staff', 'is_superuser', 'date_joined', 'last_login']
        read_only_fields = ['date_joined', 'last_login']
        
    def create(self, validated_data):
        """Create a new user with encrypted password and return it"""
        password = validated_data.pop('password', None)
        user = User.objects.create(**validated_data)
        
        if password:
            user.set_password(password)
            user.save()
            
        return user
    
    def update(self, instance, validated_data):
        """Update a user, setting the password correctly and return it"""
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        
        if password:
            user.set_password(password)
            user.save()
            
        return user

class AdminDoctorSerializer(DoctorSerializer):
    """Extended Doctor serializer with administrative fields"""
    admin_notes = serializers.CharField(required=False, allow_blank=True)
    document_count = serializers.SerializerMethodField()
    
    class Meta(DoctorSerializer.Meta):
        fields = '__all__'
        
    def get_document_count(self, obj):
        return obj.documents.count()

class AdminDoctorListSerializer(serializers.ModelSerializer):
    """Simplified Doctor serializer for list views"""
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Doctor
        fields = ['id', 'full_name', 'email', 'specialty', 'status', 'created_at']
        
    def get_full_name(self, obj):
        return f"{obj.title} {obj.first_name} {obj.last_name}"

class AdminFAQSerializer(serializers.ModelSerializer):
    """FAQ serializer with administrative fields"""
    
    class Meta:
        model = FAQ
        fields = '__all__'

class AdminSupportTicketSerializer(serializers.ModelSerializer):
    """SupportTicket serializer with administrative fields"""
    doctor_name = serializers.SerializerMethodField()
    
    class Meta:
        model = SupportTicket
        fields = '__all__'
        
    def get_doctor_name(self, obj):
        return obj.doctor.full_name if obj.doctor else None

class AdminReviewSerializer(serializers.ModelSerializer):
    """Review serializer with administrative fields"""
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    appointment_id_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = '__all__'
        
    def get_appointment_id_display(self, obj):
        return obj.appointment.appointment_id if obj.appointment.appointment_id else f"#{obj.appointment.id}"

class AdminAppointmentSerializer(serializers.ModelSerializer):
    """Appointment serializer with administrative fields"""
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    
    class Meta:
        model = Appointment
        fields = '__all__'

class AdminDashboardStatsSerializer(serializers.Serializer):
    """Serializer for admin dashboard statistics"""
    total_doctors = serializers.IntegerField()
    pending_doctors = serializers.IntegerField()
    total_appointments = serializers.IntegerField()
    total_tickets = serializers.IntegerField()
    open_tickets = serializers.IntegerField()
    total_reviews = serializers.IntegerField()
    average_rating = serializers.FloatField()
