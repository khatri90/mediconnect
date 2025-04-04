from django.db import models

class Hospital(models.Model):
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=255)
    location = models.TextField(null=True, blank=True, help_text="Google Maps link or address")
    about = models.TextField(null=True, blank=True)
    specialties = models.TextField(null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    website = models.URLField(null=True, blank=True)
    
    # Add image fields
    main_image = models.ImageField(upload_to='hospitals/%Y/%m/', null=True, blank=True)
    thumbnail = models.ImageField(upload_to='hospitals/thumbnails/%Y/%m/', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} - {self.city}"
    
    class Meta:
        verbose_name = "Hospital"
        verbose_name_plural = "Hospitals"
        ordering = ['name', 'city']

class Department(models.Model):
    """
    Model for hospital departments
    """
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    head_doctor = models.CharField(max_length=255, null=True, blank=True)
    contact_email = models.EmailField(null=True, blank=True)
    contact_phone = models.CharField(max_length=20, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} - {self.hospital.name}"
    
    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ['hospital', 'name']
        unique_together = ['hospital', 'name']