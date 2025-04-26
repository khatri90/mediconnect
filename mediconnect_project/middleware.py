import logging

logger = logging.getLogger(__name__)

class ForceFirebaseStorageMiddleware:
    """
    Middleware to force Firebase storage on every request.
    This ensures that even if the storage gets reset, we reinitialize it.
    """
    
    def __init__(self, get_response):
        # Initialize middleware
        self.get_response = get_response
    
    def __call__(self, request):
        # Code to be executed for each request before the view is called
        self._force_firebase_storage()
        
        # Get the response
        response = self.get_response(request)
        
        # Code to be executed for each request/response after the view is called
        return response
    
    def _force_firebase_storage(self):
        """Force Django to use Firebase storage."""
        from django.conf import settings
        
        # Skip in DEBUG mode to allow local development
        if settings.DEBUG:
            return
        
        try:
            # Re-import storage to ensure we have the latest
            from django.core.files.storage import default_storage
            
            # Check if storage is already Firebase
            if 'Firebase' in default_storage.__class__.__name__:
                # Already using Firebase, ensure it's initialized
                if hasattr(default_storage, 'initialized') and not default_storage.initialized:
                    default_storage._init_firebase()
            else:
                # Storage is not Firebase, let's force it
                import sys
                from mediconnect_project.firebase_storage import FirebaseMediaStorage
                
                # Create a Firebase storage instance
                firebase_storage = FirebaseMediaStorage()
                
                # Initialize it
                if not firebase_storage.initialized:
                    firebase_storage._init_firebase()
                
                # Override the default storage
                import django.core.files.storage
                from django.utils.functional import empty
                
                # Reset the default storage lazy object 
                if hasattr(django.core.files.storage, '_wrapped'):
                    django.core.files.storage._wrapped = empty
                    
                # Set our firebase storage as the default
                django.core.files.storage.default_storage._wrapped = firebase_storage
                
                logger.info(f"Middleware enforced storage: {default_storage.__class__.__name__}")
        except Exception as e:
            logger.error(f"Middleware storage enforcement error: {e}")
            import traceback
            logger.error(traceback.format_exc())