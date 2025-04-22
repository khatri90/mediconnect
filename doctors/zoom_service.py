# doctors/zoom_service.py

import requests
import json
import time
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class ZoomService:
    """Service class for interacting with the Zoom API using OAuth 2.0"""
    
    def __init__(self):
        """Initialize Zoom API credentials from settings"""
        self.client_id = settings.ZOOM_CLIENT_ID
        self.client_secret = settings.ZOOM_CLIENT_SECRET
        self.account_id = settings.ZOOM_ACCOUNT_ID  # May be needed for some API calls
        self.base_url = "https://api.zoom.us/v2"
        self.oauth_token_url = "https://zoom.us/oauth/token"
    
    def get_access_token(self):
        """
        Get OAuth access token, using cache to avoid unnecessary token requests
        """
        # Check if we have a cached token
        cached_token = cache.get('zoom_access_token')
        if cached_token:
            return cached_token
        
        # If no cached token, request a new one
        try:
            headers = {
                'Authorization': f'Basic {self._get_basic_auth_header()}'
            }
            
            payload = {
                'grant_type': 'account_credentials',
                'account_id': self.account_id
            }
            
            response = requests.post(
                self.oauth_token_url,
                headers=headers,
                data=payload
            )
            
            response.raise_for_status()
            token_data = response.json()
            
            # Get the access token and its expiration time
            access_token = token_data.get('access_token')
            expires_in = token_data.get('expires_in', 3600)  # Default to 1 hour if not specified
            
            # Cache the token for slightly less than its expiration time
            cache_duration = expires_in - 300  # 5 minutes less to ensure we refresh before expiry
            cache.set('zoom_access_token', access_token, cache_duration)
            
            return access_token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting Zoom access token: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Zoom API response: {e.response.text}")
            raise
    
    def _get_basic_auth_header(self):
        """
        Create the Basic Auth header value by encoding client_id:client_secret
        """
        import base64
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return encoded_credentials
    
    def create_meeting(self, topic, start_time, duration, doctor_email, patient_email=None):
        """
        Create a Zoom meeting and return meeting details
        
        Args:
            topic (str): Meeting topic/title
            start_time (datetime): Meeting start time (in UTC)
            duration (int): Meeting duration in minutes
            doctor_email (str): Email of the doctor (host)
            patient_email (str, optional): Email of the patient
            
        Returns:
            dict: Meeting details including meeting_id, join_url, password, etc.
        """
        access_token = self.get_access_token()
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Format start time for Zoom API (yyyy-MM-ddTHH:mm:ss)
        formatted_start_time = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        
        # Prepare meeting data
        meeting_data = {
            'topic': topic,
            'type': 2,  # Scheduled meeting
            'start_time': formatted_start_time,
            'duration': duration,
            'timezone': 'UTC',
            'password': self.generate_password(),
            'settings': {
                'host_video': True,
                'participant_video': True,
                'join_before_host': False,
                'mute_upon_entry': True,
                'waiting_room': True,
                'auto_recording': 'none',
                'email_notification': True
            }
        }
        
        # Add alternative hosts if patient email is provided
        if patient_email:
            meeting_data['settings']['alternative_hosts'] = patient_email
        
        try:
            # Use the users/me/meetings endpoint to create a meeting
            response = requests.post(
                f"{self.base_url}/users/me/meetings",
                headers=headers,
                data=json.dumps(meeting_data)
            )
            
            response.raise_for_status()  # Raise exception for non-200 status codes
            meeting_details = response.json()
            
            logger.info(f"Created Zoom meeting: {meeting_details['id']}")
            
            return {
                'meeting_id': meeting_details['id'],
                'join_url': meeting_details['join_url'],
                'password': meeting_details.get('password', ''),
                'start_url': meeting_details['start_url'],
                'status': 'scheduled'
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating Zoom meeting: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Zoom API response: {e.response.text}")
            raise
    
    def get_meeting_details(self, meeting_id):
        """Get details for a specific Zoom meeting"""
        access_token = self.get_access_token()
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/meetings/{meeting_id}",
                headers=headers
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting Zoom meeting details: {str(e)}")
            raise
    
    def update_meeting(self, meeting_id, **kwargs):
        """Update an existing Zoom meeting"""
        access_token = self.get_access_token()
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.patch(
                f"{self.base_url}/meetings/{meeting_id}",
                headers=headers,
                data=json.dumps(kwargs)
            )
            
            response.raise_for_status()
            return response.json() if response.text else {'status': 'updated'}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating Zoom meeting: {str(e)}")
            raise
    
    def delete_meeting(self, meeting_id):
        """Delete a Zoom meeting"""
        access_token = self.get_access_token()
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        
        try:
            response = requests.delete(
                f"{self.base_url}/meetings/{meeting_id}",
                headers=headers
            )
            
            response.raise_for_status()
            return {'status': 'deleted'}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error deleting Zoom meeting: {str(e)}")
            raise
    
    def generate_password(self, length=8):
        """Generate a random password for Zoom meetings"""
        import random
        import string
        
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for i in range(length))
    
    def get_meeting_participants(self, meeting_id):
        """Get the list of participants for a meeting"""
        access_token = self.get_access_token()
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/report/meetings/{meeting_id}/participants",
                headers=headers
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting Zoom meeting participants: {str(e)}")
            raise