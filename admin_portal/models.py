from django.db import models
# admin_portal/models.py

from django.db import models
from django.contrib.auth.models import AbstractBaseUser

class UserProxy(models.Model):
    """
    Proxy model for the User model from DoctorMoris
    This allows us to interact with the same database table without importing the original model
    """
    # Fields matching the exact structure of the user_accounts.User model
    email = models.EmailField(max_length=255)  # Not marking as unique since we're not creating tables
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    dob = models.DateField()
    gender = models.CharField(max_length=1)
    
    # Profile picture fields
    profile_picture = models.ImageField(upload_to='profile_pictures/%Y/%m/', null=True, blank=True)
    profile_picture_firebase_url = models.URLField(max_length=2000, null=True, blank=True)
    profile_picture_firebase_path = models.CharField(max_length=500, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    # This is important - it tells Django which table to use for this model
    class Meta:
        db_table = 'users'  # This must match the table name in DoctorMoris
        managed = False  # This tells Django not to create or manage this table

# We won't need any specific models for the admin portal
# as it will use existing models from other apps
