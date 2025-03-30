# doctors/models.py

from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from django.core.validators import MinValueValidator, MaxValueValidator


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

class DoctorAvailability(models.Model):
    DAY_CHOICES = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
        ('Sunday', 'Sunday'),
    ]
    
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='availabilities')
    day_of_week = models.CharField(max_length=20, choices=DAY_CHOICES)
    is_available = models.BooleanField(default=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('doctor', 'day_of_week')
        verbose_name = 'Doctor Availability'
        verbose_name_plural = 'Doctor Availabilities'
    
    def __str__(self):
        return f"{self.doctor.full_name} - {self.day_of_week} ({self.start_time} to {self.end_time})"


class DoctorAvailabilitySettings(models.Model):
    DURATION_CHOICES = [
        (15, '15 minutes'),
        (30, '30 minutes'),
        (45, '45 minutes'),
        (60, '60 minutes'),
    ]
    
    BUFFER_TIME_CHOICES = [
        (0, 'No buffer'),
        (5, '5 minutes'),
        (10, '10 minutes'),
        (15, '15 minutes'),
    ]
    
    BOOKING_WINDOW_CHOICES = [
        (1, '1 week'),
        (2, '2 weeks'),
        (4, '1 month'),
        (12, '3 months'),
    ]
    
    doctor = models.OneToOneField(Doctor, on_delete=models.CASCADE, related_name='availability_settings')
    appointment_duration = models.IntegerField(choices=DURATION_CHOICES, default=30)
    buffer_time = models.IntegerField(choices=BUFFER_TIME_CHOICES, default=0)
    booking_window = models.IntegerField(choices=BOOKING_WINDOW_CHOICES, default=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Settings for {self.doctor.full_name}"

# Add the Appointment model after all the other models
class Appointment(models.Model):
    
    appointment_id = models.CharField(
        max_length=6, 
        unique=True,
        help_text="Unique 6-character hexadecimal ID"
    )
    STATUS_CHOICES = [
        ('pending', 'Pending Confirmation'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]
    
    PACKAGE_TYPE_CHOICES = [
        ('in_person', 'In Person'),
        ('online', 'Online Consultation'),
    ]
    
    # Doctor from mediconnect
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='appointments')
    
    # Patient from doctomoris (represented by ID and basic info)
    patient_id = models.IntegerField()  # ID from the patient database
    patient_name = models.CharField(max_length=255)
    patient_email = models.EmailField()
    patient_phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Appointment details
    appointment_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    # Additional details
    package_type = models.CharField(max_length=20, choices=PACKAGE_TYPE_CHOICES, default='in_person')
    problem_description = models.TextField(blank=True, null=True)
    
    # Payment information
    transaction_number = models.CharField(max_length=100, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Optional notes
    doctor_notes = models.TextField(blank=True, null=True)
    admin_notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Appointment with {self.doctor.full_name} for {self.patient_name} on {self.appointment_date} at {self.start_time}"
        
    class Meta:
        # Ensure no double booking for the same doctor
        constraints = [
            models.UniqueConstraint(
                fields=['doctor', 'appointment_date', 'start_time'], 
                name='unique_appointment_slot'
            )
        ]
        indexes = [
            models.Index(fields=['doctor', 'appointment_date']),
            models.Index(fields=['patient_id', 'status']),
            models.Index(fields=['appointment_date', 'start_time']),
        ]