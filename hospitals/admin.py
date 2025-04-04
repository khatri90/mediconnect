from django.contrib import admin
from .models import Hospital, Department

class DepartmentInline(admin.TabularInline):
    model = Department
    extra = 1

@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'phone', 'email', 'has_image')
    search_fields = ('name', 'city', 'specialties')
    list_filter = ('city',)
    inlines = [DepartmentInline]
    fieldsets = (
        (None, {'fields': ('name', 'city')}),
        ('Contact Information', {'fields': ('email', 'phone', 'website')}),
        ('Details', {'fields': ('location', 'about', 'specialties')}),
        ('Images', {'fields': ('main_image', 'thumbnail')}),
    )
    
    def has_image(self, obj):
        """Display a checkmark if the hospital has an image."""
        return bool(obj.main_image)
    has_image.boolean = True
    has_image.short_description = 'Has Image'

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'hospital', 'head_doctor', 'contact_phone')
    search_fields = ('name', 'hospital__name', 'head_doctor')
    list_filter = ('hospital',)
    fieldsets = (
        (None, {'fields': ('hospital', 'name')}),
        ('Contact Information', {'fields': ('head_doctor', 'contact_email', 'contact_phone')}),
        ('Details', {'fields': ('description',)}),
    )