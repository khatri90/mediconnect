from django.contrib import admin
from django.contrib import messages
from .models import Doctor, DoctorDocument, DoctorAccount, DoctorAvailability, DoctorAvailabilitySettings
from .models import Appointment

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'patient_name', 'appointment_date', 'start_time', 'status', 'package_type']
    list_filter = ['status', 'package_type', 'appointment_date']
    search_fields = ['doctor__first_name', 'doctor__last_name', 'patient_name', 'patient_email']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Appointment Information', {
            'fields': (
                'doctor', 
                ('appointment_date', 'start_time', 'end_time'),
                'status',
                'package_type'
            )
        }),
        ('Patient Information', {
            'fields': (
                'patient_id',
                'patient_name',
                'patient_email',
                'patient_phone'
            )
        }),
        ('Details', {
            'fields': (
                'problem_description',
                'transaction_number',
                'amount'
            )
        }),
        ('Notes', {
            'fields': (
                'doctor_notes',
                'admin_notes'
            )
        }),
        ('Metadata', {
            'fields': (
                ('created_at', 'updated_at'),
            ),
            'classes': ('collapse',)
        }),
    )
class DoctorDocumentInline(admin.TabularInline):
    model = DoctorDocument
    extra = 0
    readonly_fields = ['uploaded_at']

class DoctorAccountInline(admin.StackedInline):
    model = DoctorAccount
    can_delete = False
    verbose_name_plural = 'Doctor Account'
    fields = ['username', 'last_login', 'is_active', 'created_at']
    readonly_fields = ['username', 'last_login', 'created_at']
    
    def has_add_permission(self, request, obj=None):
        # Prevent adding accounts manually - they are created via signals
        return False

class DoctorAvailabilityInline(admin.TabularInline):
    model = DoctorAvailability
    extra = 0
    fields = ['day_of_week', 'is_available', 'start_time', 'end_time']

class DoctorAvailabilitySettingsInline(admin.StackedInline):
    model = DoctorAvailabilitySettings
    can_delete = False
    verbose_name_plural = 'Availability Settings'
    fields = ['appointment_duration', 'buffer_time', 'booking_window', 'created_at', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']
    
@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'specialty', 'status', 'created_at']
    list_filter = ['status', 'specialty', 'country']
    search_fields = ['first_name', 'last_name', 'email', 'license_number']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [DoctorDocumentInline, DoctorAccountInline, DoctorAvailabilityInline, DoctorAvailabilitySettingsInline]
    actions = ['approve_doctors']
    
    fieldsets = (
        ('Personal Information', {
            'fields': (
                ('title', 'first_name', 'last_name'),
                ('email', 'phone'),
                'date_of_birth', 'gender',
                'address', 'city', 'state', 'zip_code', 'country', 'nationality'
            )
        }),
        ('Professional Information', {
            'fields': (
                ('specialty', 'secondary_specialty'),
                ('license_number', 'license_state'),
                'years_experience', 'languages',
                'clinic_name', 'clinic_address', 'clinic_city', 'clinic_state', 'clinic_zip',
                ('clinic_phone', 'clinic_email')
            )
        }),
        ('Educational Background', {
            'fields': (
                ('medical_school', 'graduation_year'),
                'degree', 'residency', 'fellowship', 'board_certification',
                'other_qualifications'
            )
        }),
        ('About & Services', {
            'fields': (
                'about_me', 'services', 'insurances', 'hospital_affiliations'
            )
        }),
        ('Subscription & Status', {
            'fields': (
                'subscription_plan', 'status',
                ('terms_agreed', 'data_consent', 'verification_consent'),
                ('created_at', 'updated_at')
            )
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Override save_model to check if a password was generated"""
        super().save_model(request, obj, form, change)
        
        # Check if a password was generated during save (by the signal)
        if hasattr(obj, '_generated_password'):
            messages.success(
                request, 
                f"Account created for {obj.full_name}.<br>"
                f"Email: {obj.email}<br>"
                f"Password: <code>{obj._generated_password}</code><br>"
                f"Please communicate this password securely to the doctor."
            )
    
    def approve_doctors(self, modeladmin, request, queryset):
        """Batch approve selected doctors"""
        for doctor in queryset:
            if doctor.status == 'approved':
                continue
            doctor.status = 'approved'
            doctor.save()
        
        messages.success(request, f"{queryset.count()} doctors have been approved. Account details will be shown above.")
    
    approve_doctors.short_description = "Approve selected doctors"
    
    def full_name(self, obj):
        return f"{obj.title} {obj.first_name} {obj.last_name}"
    full_name.short_description = "Name"

@admin.register(DoctorDocument)
class DoctorDocumentAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'document_type', 'uploaded_at']
    list_filter = ['document_type', 'uploaded_at']
    search_fields = ['doctor__first_name', 'doctor__last_name', 'doctor__email']

@admin.register(DoctorAccount)
class DoctorAccountAdmin(admin.ModelAdmin):
    list_display = ['doctor_name', 'username', 'is_active', 'last_login', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['doctor__first_name', 'doctor__last_name', 'username']
    readonly_fields = ['doctor', 'username', 'last_login', 'created_at']
    
    def doctor_name(self, obj):
        return obj.doctor.full_name
    doctor_name.short_description = "Doctor"
    
    def has_add_permission(self, request):
        # Accounts are created automatically
        return False

@admin.register(DoctorAvailability)
class DoctorAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'day_of_week', 'is_available', 'start_time', 'end_time']
    list_filter = ['day_of_week', 'is_available']
    search_fields = ['doctor__first_name', 'doctor__last_name', 'doctor__email']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(DoctorAvailabilitySettings)
class DoctorAvailabilitySettingsAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'appointment_duration', 'buffer_time', 'booking_window']
    search_fields = ['doctor__first_name', 'doctor__last_name', 'doctor__email']
    readonly_fields = ['created_at', 'updated_at']
