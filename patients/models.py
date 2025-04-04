from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password

class PatientManager(BaseUserManager):
    def create_patient(self, email, name, phone_number, dob, gender, password=None, **extra_fields):
        """
        Create and save a Patient with the given email, name, and password.
        """
        if not email:
            raise ValueError('Patients must have an email address')
        
        email = self.normalize_email(email)
        patient = self.model(
            email=email,
            name=name,
            phone_number=phone_number,
            dob=dob,
            gender=gender,
            **extra_fields
        )
        patient.set_password(password)
        patient.save(using=self._db)
        return patient

class Patient(AbstractBaseUser):
    """
    Custom Patient model that uses email as the unique identifier
    instead of username.
    """
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    )
    
    email = models.EmailField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    dob = models.DateField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Added for admin access if needed
    is_superuser = models.BooleanField(default=False)  # Added simple field to replace PermissionsMixin
    date_joined = models.DateTimeField(default=timezone.now)
    
    # For medical data
    allergies = models.TextField(blank=True, null=True)
    medical_conditions = models.TextField(blank=True, null=True)
    medications = models.TextField(blank=True, null=True)
    blood_type = models.CharField(max_length=5, blank=True, null=True)
    
    objects = PatientManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name', 'dob', 'gender']
    
    def __str__(self):
        return self.email
    
    class Meta:
        db_table = 'patients_patient'  # Changed to match actual table name in database

    def has_perm(self, perm, obj=None):
        """
        Simple permission check replacement
        """
        return self.is_superuser

    def has_module_perms(self, app_label):
        """
        Simple permission check replacement
        """
        return self.is_superuser

class PatientAccount(models.Model):
    """
    Account model for patients, similar to DoctorAccount.
    This allows for consistent account management between doctors and patients.
    """
    patient = models.OneToOneField(Patient, on_delete=models.CASCADE, related_name='account')
    username = models.CharField(max_length=100, unique=True)  # We'll use email as username
    password_hash = models.CharField(max_length=128)  # Stores hashed password
    last_login = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Account for {self.patient.name}"
    
    def set_password(self, raw_password):
        """Set a hashed password"""
        self.password_hash = make_password(raw_password)
        self.save(update_fields=['password_hash'])
    
    def check_password(self, raw_password):
        """Check if the provided password matches the stored hash"""
        return check_password(raw_password, self.password_hash)

class MedicalRecord(models.Model):
    """
    Model to store patient medical records
    """
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='medical_records')
    doctor_name = models.CharField(max_length=255)  # Name of the doctor who created the record
    doctor_id = models.IntegerField(null=True, blank=True)  # Optional link to doctor in our system
    record_date = models.DateField()
    diagnosis = models.TextField()
    treatment = models.TextField()
    prescription = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Medical Record for {self.patient.name} on {self.record_date}"
    
    class Meta:
        ordering = ['-record_date']

class PatientDocument(models.Model):
    """
    Model to store patient documents like insurance cards, medical reports, etc.
    """
    DOCUMENT_TYPE_CHOICES = [
        ('insurance_card', 'Insurance Card'),
        ('medical_report', 'Medical Report'),
        ('lab_result', 'Lab Result'),
        ('prescription', 'Prescription'),
        ('other', 'Other'),
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='patient_documents/')
    notes = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.patient.name} - {self.get_document_type_display()} - {self.title}"