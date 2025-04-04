from django.contrib import admin
from .models import Patient, PatientAccount, MedicalRecord, PatientDocument

class PatientDocumentInline(admin.TabularInline):
    model = PatientDocument
    extra = 0
    readonly_fields = ['uploaded_at']

class MedicalRecordInline(admin.TabularInline):
    model = MedicalRecord
    extra = 0
    readonly_fields = ['created_at', 'updated_at']

class PatientAccountInline(admin.StackedInline):
    model = PatientAccount
    can_delete = False
    verbose_name_plural = 'Patient Account'
    fields = ['username', 'last_login', 'is_active', 'created_at']
    readonly_fields = ['username', 'last_login', 'created_at']
    
    def has_add_permission(self, request, obj=None):
        # Prevent adding accounts manually - they are created via signals
        return False

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone_number', 'gender', 'is_active', 'date_joined']
    list_filter = ['gender', 'is_active', 'date_joined']
    search_fields = ['name', 'email', 'phone_number']
    readonly_fields = ['date_joined']
    inlines = [PatientAccountInline, PatientDocumentInline, MedicalRecordInline]
    
    fieldsets = (
        ('Personal Information', {
            'fields': (
                'name', 'email', 'phone_number',
                'dob', 'gender', 'is_active'
            )
        }),
        ('Medical Information', {
            'fields': (
                'allergies', 'medical_conditions',
                'medications', 'blood_type'
            )
        }),
        ('Metadata', {
            'fields': ('date_joined',),
            'classes': ('collapse',)
        }),
    )

@admin.register(PatientDocument)
class PatientDocumentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'document_type', 'title', 'uploaded_at']
    list_filter = ['document_type', 'uploaded_at']
    search_fields = ['patient__name', 'patient__email', 'title']
    readonly_fields = ['uploaded_at']

@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ['patient', 'doctor_name', 'record_date', 'diagnosis']
    list_filter = ['record_date']
    search_fields = ['patient__name', 'doctor_name', 'diagnosis', 'treatment']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(PatientAccount)
class PatientAccountAdmin(admin.ModelAdmin):
    list_display = ['patient_name', 'username', 'is_active', 'last_login', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['patient__name', 'username']
    readonly_fields = ['patient', 'username', 'last_login', 'created_at']
    
    def patient_name(self, obj):
        return obj.patient.name
    patient_name.short_description = "Patient"
    
    def has_add_permission(self, request):
        # Accounts are created automatically
        return False