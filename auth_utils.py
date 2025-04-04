import jwt
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

JWT_SECRET = getattr(settings, 'JWT_SECRET', settings.SECRET_KEY)
JWT_ALGORITHM = 'HS256'

def get_token_from_request(request):
    """Extract the token from either headers or META"""
    # Try the headers attribute first (DRF's Request)
    auth_header = request.headers.get('Authorization')
    
    # If not found, try the META dictionary (Django's HttpRequest)
    if not auth_header:
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
            
    return auth_header.split(' ')[1]

def verify_token(token, token_type='doctor'):
    """
    Verify a JWT token and return the id
    
    Args:
        token: The JWT token to verify
        token_type: Either 'doctor' or 'patient' depending on token type
    
    Returns:
        The doctor_id or patient_id if valid, None otherwise
    """
    if not token:
        return None
        
    try:
        logger.debug(f"Verifying {token_type} token: {token[:10]}...")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        # Get the appropriate ID based on token type
        id_field = f"{token_type}_id"
        user_id = payload.get(id_field)
        
        logger.debug(f"Token verified successfully, {id_field}: {user_id}")
        return user_id
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error verifying token: {str(e)}")
        return None