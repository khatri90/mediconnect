from rest_framework import status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from django.conf import settings
import jwt
import datetime

from .models import Patient, PatientAccount, MedicalRecord, PatientDocument
from .serializers import (
    PatientSerializer, 
    PatientProfileSerializer,
    PatientLoginSerializer, 
    PatientRegistrationSerializer,
    MedicalRecordSerializer,
    PatientDocumentSerializer,
    PatientDocumentUploadSerializer
)

# Use the same JWT settings as the doctor app for consistency
JWT_SECRET = getattr(settings, 'JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_DELTA = datetime.timedelta(days=7)

def generate_patient_token(patient_id):
    """Generate a JWT token for the patient"""
    payload = {
        'patient_id': patient_id,
        'exp': datetime.datetime.utcnow() + JWT_EXPIRATION_DELTA
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_patient_token(token):
    """Verify a JWT token and return the patient_id"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('patient_id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

class PatientRegistrationView(APIView):
    """
    API view to handle patient registration
    """
    permission_classes = [permissions.AllowAny]
    parser_classes = (MultiPartParser, FormParser)
    
    def post(self, request, format=None):
        serializer = PatientRegistrationSerializer(data=request.data)
        
        if serializer.is_valid():
            # Create the patient
            # Create the patient
            patient = serializer.save()
            # Store password for signal handler
            patient._password = serializer.validated_data['password']
            
            # Generate token
            token = generate_patient_token(patient.id)
            
            return Response({
                'status': 'success',
                'message': 'Registration successful',
                'token': token,
                'patient_id': patient.id,
                'email': patient.email,
                'name': patient.name
            }, status=status.HTTP_201_CREATED)
            
        return Response({
            'status': 'error',
            'message': 'Registration failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

class PatientLoginView(APIView):
    """
    API view to handle patient login
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, format=None):
        serializer = PatientLoginSerializer(data=request.data)
        
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            
            try:
                # Find patient by email
                patient = Patient.objects.get(email=email)
                
                # Find account
                account = PatientAccount.objects.get(patient=patient)
                
                # Verify password
                if not account.check_password(password):
                    return Response({
                        'status': 'error',
                        'message': 'Invalid credentials'
                    }, status=status.HTTP_401_UNAUTHORIZED)
                
                # Update last login time
                account.last_login = timezone.now()
                account.save(update_fields=['last_login'])
                
                # Generate JWT token
                token = generate_patient_token(patient.id)
                
                # Return success response with patient details and token
                return Response({
                    'status': 'success',
                    'message': 'Login successful',
                    'token': token,
                    'patient_id': patient.id,
                    'name': patient.name,
                    'email': patient.email
                }, status=status.HTTP_200_OK)
                    
            except Patient.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': 'No account found for this email'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            except PatientAccount.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': 'No account found for this patient'
                }, status=status.HTTP_401_UNAUTHORIZED)
        
        return Response({
            'status': 'error',
            'message': 'Invalid data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

class PatientProfileView(APIView):
    """
    API view to retrieve and update patient profile information
    """
    def get(self, request, format=None):
        # Get token from authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return Response({
                'status': 'error',
                'message': 'Authentication token required'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        token = auth_header.split(' ')[1]
        patient_id = verify_patient_token(token)
        
        if not patient_id:
            return Response({
                'status': 'error',
                'message': 'Invalid or expired token'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            # Find patient by ID
            patient = Patient.objects.get(id=patient_id)
            
            # Serialize patient data
            serializer = PatientProfileSerializer(patient)
            
            return Response({
                'status': 'success',
                'patient': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Patient.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Patient not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    def put(self, request, format=None):
        # Get token from authorization header
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return Response({
                'status': 'error',
                'message': 'Authentication token required'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        token = auth_header.split(' ')[1]
        patient_id = verify_patient_token(token)
        
        if not patient_id:
            return Response({
                'status': 'error',
                'message': 'Invalid or expired token'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            # Find patient by ID
            patient = Patient.objects.get(id=patient_id)
            
            # Update patient data
            serializer = PatientProfileSerializer(patient, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                
                return Response({
                    'status': 'success',
                    'message': 'Profile updated successfully',
                    'patient': serializer.data
                }, status=status.HTTP_200_OK)
                
            return Response({
                'status': 'error',
                'message': 'Invalid data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Patient.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Patient not found'
            }, status=status.HTTP_404_NOT_FOUND)

class PatientMedicalRecordViewSet(viewsets.ModelViewSet):
    """
    ViewSet to manage patient medical records
    """
    serializer_class = MedicalRecordSerializer
    
    def get_queryset(self):
        # Get token from authorization header
        auth_header = self.request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return MedicalRecord.objects.none()
            
        token = auth_header.split(' ')[1]
        patient_id = verify_patient_token(token)
        
        if not patient_id:
            return MedicalRecord.objects.none()
        
        return MedicalRecord.objects.filter(patient_id=patient_id)
    
    def perform_create(self, serializer):
        # Get token from authorization header
        auth_header = self.request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            raise permissions.PermissionDenied("Authentication token required")
            
        token = auth_header.split(' ')[1]
        patient_id = verify_patient_token(token)
        
        if not patient_id:
            raise permissions.PermissionDenied("Invalid or expired token")
        
        try:
            patient = Patient.objects.get(id=patient_id)
            serializer.save(patient=patient)
        except Patient.DoesNotExist:
            raise ValueError("Patient not found")

class PatientDocumentView(APIView):
    """
    API view to handle patient document uploads and listing
    """
    parser_classes = (MultiPartParser, FormParser)
    
    def get(self, request, format=None):
        # Get token from authorization header
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return Response({
                'status': 'error',
                'message': 'Authentication token required'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        token = auth_header.split(' ')[1]
        patient_id = verify_patient_token(token)
        
        if not patient_id:
            return Response({
                'status': 'error',
                'message': 'Invalid or expired token'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            # Find patient by ID
            patient = Patient.objects.get(id=patient_id)
            
            # Get documents
            documents = PatientDocument.objects.filter(patient=patient)
            
            # Serialize documents
            serializer = PatientDocumentSerializer(documents, many=True)
            
            return Response({
                'status': 'success',
                'documents': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Patient.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Patient not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    def post(self, request, format=None):
        # Get token from authorization header
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return Response({
                'status': 'error',
                'message': 'Authentication token required'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        token = auth_header.split(' ')[1]
        patient_id = verify_patient_token(token)
        
        if not patient_id:
            return Response({
                'status': 'error',
                'message': 'Invalid or expired token'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            # Find patient by ID
            patient = Patient.objects.get(id=patient_id)
            
            # Create serializer with data
            serializer = PatientDocumentUploadSerializer(data=request.data)
            
            if serializer.is_valid():
                # Save document with patient reference
                document = serializer.save(patient=patient)
                
                return Response({
                    'status': 'success',
                    'message': 'Document uploaded successfully',
                    'document': PatientDocumentSerializer(document).data
                }, status=status.HTTP_201_CREATED)
                
            return Response({
                'status': 'error',
                'message': 'Invalid data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Patient.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Patient not found'
            }, status=status.HTTP_404_NOT_FOUND)

class ForgotPasswordView(APIView):
    """
    API view to handle password reset requests
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, format=None):
        email = request.data.get('email')
        
        if not email:
            return Response({
                'status': 'error',
                'message': 'Email is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            patient = Patient.objects.get(email=email)
            
            # Generate a password reset token (would normally send an email)
            token = generate_patient_token(patient.id)
            
            # In a real implementation, send an email with reset link
            # For this example, we'll just return a success message
            
            return Response({
                'status': 'success',
                'message': 'Password reset instructions sent to your email'
            }, status=status.HTTP_200_OK)
            
        except Patient.DoesNotExist:
            # For security reasons, don't reveal that the email doesn't exist
            return Response({
                'status': 'success',
                'message': 'Password reset instructions sent to your email'
            }, status=status.HTTP_200_OK)