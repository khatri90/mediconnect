from django.contrib import admin
from django.contrib import messages
from .models import Doctor, DoctorDocument, DoctorAccount, DoctorAvailability, DoctorAvailabilitySettings
from .models import Appointment
from .models import Review
from .models import SupportTicket, FAQ

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['appointment_id', 'doctor', 'patient_name', 'appointment_date', 'start_time', 'status', 'package_type']
    list_filter = ['status', 'package_type', 'appointment_date']
    search_fields = ['appointment_id', 'doctor__first_name', 'doctor__last_name', 'patient_name', 'patient_email']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Appointment Information', {
            'fields': (
                'appointment_id',
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
        ('Zoom Meeting', {  # Add this new fieldset
            'fields': (
                'zoom_meeting_id',
                'zoom_meeting_url',
                'zoom_meeting_password',
                'zoom_meeting_status',
                ('zoom_host_joined', 'zoom_client_joined'),
                'zoom_meeting_duration'
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
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['appointment_id_display', 'doctor_name', 'patient_id', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['doctor__first_name', 'doctor__last_name', 'appointment__appointment_id', 'review_text']
    readonly_fields = ['created_at', 'updated_at']
    
    def appointment_id_display(self, obj):
        """Display appointment ID in a more readable format"""
        return obj.appointment.appointment_id if obj.appointment.appointment_id else f"#{obj.appointment.id}"
    appointment_id_display.short_description = "Appointment"
    
    def doctor_name(self, obj):
        """Display doctor's full name"""
        return obj.doctor.full_name
    doctor_name.short_description = "Doctor"
    
    
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
    list_display = ['full_name', 'email', 'specialty', 'status', 'rating_display', 'created_at']
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
    
    def rating_display(self, obj):
        """Display doctor's rating in a readable format"""
        if obj.average_rating is None:
            return "No ratings"
        return f"{obj.average_rating:.1f} ★ ({obj.total_reviews})"
    rating_display.short_description = "Rating"
    
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

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ['ticket_id', 'full_name', 'subject', 'status', 'user_type', 'created_at']
    list_filter = ['status', 'subject', 'user_type', 'created_at']
    search_fields = ['ticket_id', 'full_name', 'email', 'message']
    readonly_fields = ['ticket_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Ticket Information', {
            'fields': (
                'ticket_id',
                'subject',
                'status',
                'user_type',
            )
        }),
        ('User Information', {
            'fields': (
                'full_name',
                'email',
                'doctor',
                'patient_id',
            )
        }),
        ('Message Details', {
            'fields': (
                'message',
                'attachments',
            )
        }),
        ('Response', {
            'fields': (
                'response',
                'agent_notes',
                'resolved_at',
            )
        }),
        ('Metadata', {
            'fields': (
                ('created_at', 'updated_at'),
            ),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        # Set resolved_at date when status changes to resolved
        if 'status' in form.changed_data and obj.status == 'resolved' and not obj.resolved_at:
            obj.resolved_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ['question', 'category', 'order', 'is_published']
    list_filter = ['category', 'is_published']
    search_fields = ['question', 'answer']
    list_editable = ['order', 'is_published']
    
    fieldsets = (
        (None, {
            'fields': (
                'question',
                'answer',
                'category',
            )
        }),
        ('Display Options', {
            'fields': (
                'order',
                'is_published',
            )
        }),
    )
