# doctors/models.py

from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password


class Doctor(models.Model):
    # User choices
    TITLE_CHOICES = [
        ('Dr.', 'Dr.'),
        ('Prof.', 'Prof.'),
        ('Mr.', 'Mr.'),
        ('Mrs.', 'Mrs.'),
        ('Ms.', 'Ms.'),
    ]
    
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
        ('Prefer not to say', 'Prefer not to say'),
    ]
    
    EXPERIENCE_CHOICES = [
        ('0-2', '0-2 years'),
        ('3-5', '3-5 years'),
        ('6-10', '6-10 years'),
        ('11-15', '11-15 years'),
        ('16-20', '16-20 years'),
        ('20+', '20+ years'),
    ]
    
    SUBSCRIPTION_CHOICES = [
        ('basic', 'Basic Plan - $29/month'),
        ('professional', 'Professional Plan - $49/month'),
        ('premium', 'Premium Plan - $99/month'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    # Personal Information (Step 1)
    title = models.CharField(max_length=10, choices=TITLE_CHOICES)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    nationality = models.CharField(max_length=100, blank=True, null=True)
    
    # Professional Information (Step 2)
    specialty = models.CharField(max_length=100)
    secondary_specialty = models.CharField(max_length=100, blank=True, null=True)
    license_number = models.CharField(max_length=100)
    license_state = models.CharField(max_length=100)
    years_experience = models.CharField(max_length=10, choices=EXPERIENCE_CHOICES)
    languages = models.CharField(max_length=255)
    clinic_name = models.CharField(max_length=255)
    clinic_address = models.CharField(max_length=255)
    clinic_city = models.CharField(max_length=100)
    clinic_state = models.CharField(max_length=100)
    clinic_zip = models.CharField(max_length=20)
    clinic_phone = models.CharField(max_length=20)
    clinic_email = models.EmailField(blank=True, null=True)
    
    # Educational Background (Step 3)
    medical_school = models.CharField(max_length=255)
    graduation_year = models.IntegerField()
    degree = models.CharField(max_length=255)
    residency = models.CharField(max_length=255, blank=True, null=True)
    fellowship = models.CharField(max_length=255, blank=True, null=True)
    board_certification = models.CharField(max_length=255, blank=True, null=True)
    other_qualifications = models.TextField(blank=True, null=True)
    
    # About Me & Services (Step 4)
    about_me = models.TextField()
    services = models.TextField()
    insurances = models.TextField(blank=True, null=True)
    hospital_affiliations = models.TextField(blank=True, null=True)
    
    # Document Uploads will be handled in a separate model
    
    # Subscription Plan & Terms (Step 6)
    subscription_plan = models.CharField(max_length=20, choices=SUBSCRIPTION_CHOICES, default='professional')
    terms_agreed = models.BooleanField(default=False)
    data_consent = models.BooleanField(default=False)
    verification_consent = models.BooleanField(default=False)
    
    # Additional fields
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} {self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        return f"{self.title} {self.first_name} {self.last_name}"


class DoctorDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ('profile_photo', 'Profile Photo'),
        ('medical_license', 'Medical License'),
        ('medical_degree', 'Medical Degree Certificate'),
        ('additional_certificate', 'Additional Certificate'),
    ]
    
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES)
    file = models.FileField(upload_to='doctor_documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.doctor.full_name} - {self.get_document_type_display()}"

class DoctorAccount(models.Model):
    doctor = models.OneToOneField(Doctor, on_delete=models.CASCADE, related_name='account')
    username = models.CharField(max_length=100, unique=True)  # We'll use email as username
    password_hash = models.CharField(max_length=128)  # Stores hashed password
    last_login = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Account for {self.doctor.full_name}"
    
    def set_password(self, raw_password):
        """Set a hashed password"""
        self.password_hash = make_password(raw_password)
        self.save(update_fields=['password_hash'])
    
    def check_password(self, raw_password):
        """Check if the provided password matches the stored hash"""
        return check_password(raw_password, self.password_hash)    