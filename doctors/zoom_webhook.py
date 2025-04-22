# doctors/zoom_webhook.py

import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from .appointment_service import AppointmentService
from .models import Appointment

logger = logging.getLogger(__name__)
appointment_service = AppointmentService()

@csrf_exempt
def zoom_webhook_handler(request):
    """
    Handle Zoom webhook events and validation challenges
    
    Zoom webhooks include events like:
    - meeting.started
    - meeting.ended
    - meeting.participant_joined
    - meeting.participant_left
    
    These events help us track meeting attendance and status
    """
    # Handle the webhook validation challenge
    if request.method == 'POST' and request.headers.get('content-type') == 'application/json':
        try:
            data = json.loads(request.body)
            
            # Check if this is a validation request
            if data.get('event') == 'endpoint.url_validation':
                return handle_validation_challenge(data)
            
            # Continue with normal webhook processing
            return process_webhook_event(request, data)
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            return HttpResponse("Bad Request: Invalid JSON", status=400)
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            return HttpResponse("Internal Server Error", status=500)
    
    # Handle unsupported methods
    return HttpResponse("Method Not Allowed", status=405)

def handle_validation_challenge(data):
    """
    Handle the Zoom webhook validation challenge
    
    When you set up a webhook endpoint, Zoom sends a validation request
    with a challenge code that you need to hash and return
    """
    try:
        # Extract challenge details
        plain_token = data.get('payload', {}).get('plainToken')
        
        if not plain_token:
            logger.error("Missing plainToken in validation payload")
            return HttpResponse("Bad Request: Missing plain token", status=400)
        
        # Construct the response with the plain token
        response_data = {
            "plainToken": plain_token
        }
        
        logger.info("Successfully responded to Zoom validation challenge")
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error handling validation challenge: {str(e)}")
        return HttpResponse("Internal Server Error", status=500)

def process_webhook_event(request, data):
    """Process a regular webhook event notification"""
    # Get the event type
    event = data.get('event')
    
    if not event:
        logger.error("Invalid webhook payload: missing event")
        return HttpResponse("Bad Request: Missing event", status=400)
    
    # Verify the webhook using the X-Zoom-Signature-256 header
    zoom_signature = request.headers.get('X-Zoom-Signature-256')
    if not verify_zoom_webhook(request.body, zoom_signature):
        logger.warning("Received unverified webhook request")
        return HttpResponse("Unauthorized", status=401)
    
    logger.info(f"Received Zoom webhook: {event}")
    
    # Get meeting details from payload
    meeting_id = None
    if 'payload' in data and 'object' in data['payload']:
        meeting_id = data['payload']['object'].get('id')
    
    if not meeting_id:
        logger.error("Invalid webhook payload: missing meeting ID")
        return HttpResponse("Bad Request: Missing meeting ID", status=400)
    
    # Process different event types
    if event == 'meeting.started':
        handle_meeting_started(meeting_id, data)
    elif event == 'meeting.ended':
        handle_meeting_ended(meeting_id, data)
    elif event == 'meeting.participant_joined':
        handle_participant_joined(meeting_id, data)
    elif event == 'meeting.participant_left':
        handle_participant_left(meeting_id, data)
    
    return HttpResponse("Event received", status=200)

def verify_zoom_webhook(request_body, signature_header):
    """
    Verify that the webhook request came from Zoom using the X-Zoom-Signature-256 header
    
    Args:
        request_body: The raw request body bytes
        signature_header: The X-Zoom-Signature-256 header value
    
    Returns:
        bool: True if the signature is valid, False otherwise
    """
    import hmac
    import hashlib
    
    if not settings.ZOOM_WEBHOOK_SECRET_TOKEN or not signature_header:
        logger.warning("Missing ZOOM_WEBHOOK_SECRET_TOKEN or signature header")
        return False
    
    # Remove the 'v0=' prefix if present
    if signature_header.startswith('v0='):
        signature_header = signature_header[3:]
    
    # Compute the expected signature
    computed_hash = hmac.new(
        settings.ZOOM_WEBHOOK_SECRET_TOKEN.encode('utf-8'),
        request_body,
        hashlib.sha256
    ).hexdigest()
    
    # Compare the computed hash with the signature
    return hmac.compare_digest(computed_hash, signature_header)

def handle_meeting_started(meeting_id, payload):
    """Handle meeting.started event"""
    try:
        # Find the appointment by Zoom meeting ID
        appointment = Appointment.objects.get(zoom_meeting_id=meeting_id)
        
        # Update meeting status
        appointment.zoom_meeting_status = 'started'
        appointment.save()
        
        logger.info(f"Meeting started: {meeting_id}")
        
    except Appointment.DoesNotExist:
        logger.error(f"Appointment with Zoom meeting ID not found: {meeting_id}")
    except Exception as e:
        logger.error(f"Error handling meeting.started: {str(e)}")

def handle_meeting_ended(meeting_id, payload):
    """Handle meeting.ended event"""
    try:
        # Find the appointment by Zoom meeting ID
        appointment = Appointment.objects.get(zoom_meeting_id=meeting_id)
        
        # If both parties joined, mark as completed, otherwise mark as missed
        if appointment.zoom_host_joined and appointment.zoom_client_joined:
            appointment.zoom_meeting_status = 'completed'
            # Also mark the appointment as completed
            appointment.status = 'completed'
        else:
            appointment.zoom_meeting_status = 'missed'
        
        # Get meeting duration from payload if available
        duration = payload.get('payload', {}).get('object', {}).get('duration')
        if duration:
            appointment.zoom_meeting_duration = duration
        
        appointment.save()
        
        logger.info(f"Meeting ended: {meeting_id}")
        
    except Appointment.DoesNotExist:
        logger.error(f"Appointment with Zoom meeting ID not found: {meeting_id}")
    except Exception as e:
        logger.error(f"Error handling meeting.ended: {str(e)}")

def handle_participant_joined(meeting_id, payload):
    """Handle meeting.participant_joined event"""
    try:
        # Get participant information
        participant_info = payload.get('payload', {}).get('object', {}).get('participant', {})
        email = participant_info.get('email', '').lower()
        user_id = participant_info.get('user_id', '')
        
        # Find the appointment by Zoom meeting ID
        appointment = Appointment.objects.get(zoom_meeting_id=meeting_id)
        
        # Check if the participant is the doctor or patient
        if email == appointment.doctor.email.lower():
            appointment.zoom_host_joined = True
        elif email == appointment.patient_email.lower():
            appointment.zoom_client_joined = True
        
        appointment.save()
        
        logger.info(f"Participant joined meeting: {meeting_id}, Email: {email}")
        
    except Appointment.DoesNotExist:
        logger.error(f"Appointment with Zoom meeting ID not found: {meeting_id}")
    except Exception as e:
        logger.error(f"Error handling meeting.participant_joined: {str(e)}")

def handle_participant_left(meeting_id, payload):
    """Handle meeting.participant_left event"""
    # We don't need to track when participants leave
    # The meeting.ended event will give us the final attendance status
    pass