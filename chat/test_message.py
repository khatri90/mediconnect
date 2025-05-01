#!/usr/bin/env python
"""
Test script to send a chat message from a doctor to a patient and trigger notification.
Run this from the mediconnect-doctors server directory.
"""

import os
import sys
import django
import requests
import json
import logging
import argparse
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediconnect.settings')
django.setup()

# Now import Django models
from chat.models import Chat
from chat.firebase_utils import FirebaseChat
from doctors.models import Appointment, Doctor
from django.conf import settings

def send_test_message(chat_id=None, appointment_id=None, doctor_id=None, message=None):
    """
    Send a test message from a doctor to a patient
    
    Args:
        chat_id: Firebase chat ID (if you already know it)
        appointment_id: Appointment ID (if you don't have the chat ID)
        doctor_id: Doctor ID (if not provided, will use the appointment's doctor)
        message: Message text to send (defaults to a test message)
    """
    # Validate inputs
    if not chat_id and not appointment_id:
        logger.error("Either chat_id or appointment_id must be provided")
        return False
    
    # Default message
    if not message:
        message = f"This is a test message sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    try:
        # Get the chat object
        chat = None
        appointment = None
        
        if chat_id:
            try:
                chat = Chat.objects.get(firebase_chat_id=chat_id)
                appointment = chat.appointment
                logger.info(f"Found chat with ID {chat_id} for appointment {appointment.appointment_id}")
            except Chat.DoesNotExist:
                logger.error(f"Chat with ID {chat_id} not found")
                return False
        
        elif appointment_id:
            try:
                # Try to find by appointment_id field
                appointment = Appointment.objects.get(appointment_id=appointment_id)
            except Appointment.DoesNotExist:
                try:
                    # Try to find by ID
                    appointment = Appointment.objects.get(id=appointment_id)
                except (Appointment.DoesNotExist, ValueError):
                    logger.error(f"Appointment with ID {appointment_id} not found")
                    return False
            
            try:
                chat = Chat.objects.get(appointment=appointment)
                chat_id = chat.firebase_chat_id
                logger.info(f"Found chat {chat_id} for appointment {appointment.appointment_id}")
            except Chat.DoesNotExist:
                logger.error(f"No chat found for appointment {appointment.appointment_id}")
                return False
        
        # Get doctor ID
        if not doctor_id:
            doctor_id = appointment.doctor.id
        
        # Send message using FirebaseChat
        logger.info(f"Sending message as doctor {doctor_id} to patient {appointment.patient_id}")
        result = FirebaseChat.send_message(
            chat_id=chat_id,
            user_id=doctor_id,
            user_type='doctor',
            text=message
        )
        
        if not result:
            logger.error("Failed to send message to Firebase")
            return False
        
        logger.info("Message sent successfully to Firebase")
        
        # Now send the notification
        doctomoris_api_key = getattr(settings, 'DOCTOMORIS_API_KEY', os.environ.get('DOCTOMORIS_API_KEY', ''))
        
        if not doctomoris_api_key:
            logger.error("DOCTOMORIS_API_KEY not configured")
            return False
        
        # Get doctor name
        doctor = appointment.doctor
        doctor_name = getattr(doctor, 'full_name', None) or doctor.last_name
        
        # Prepare notification data
        notification_data = {
            'patient_id': appointment.patient_id,
            'doctor_name': doctor_name,
            'message_preview': message,
            'appointment_id': appointment.appointment_id,
            'chat_id': chat_id
        }
        
        # Set up headers
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {doctomoris_api_key}"
        }
        
        # URL for the notification endpoint
        notification_url = "https://doctomoris.onrender.com/api/notifications/chat-message/"
        
        # Send notification request
        logger.info(f"Sending notification request to {notification_url}")
        response = requests.post(
            notification_url,
            json=notification_data,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            logger.info(f"Notification request successful: {response.json()}")
            return True
        else:
            logger.error(f"Notification request failed: {response.status_code} - {response.text}")
            return False
        
    except Exception as e:
        logger.error(f"Error sending test message: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def list_available_chats():
    """List available chats to help choose one for testing"""
    try:
        chats = Chat.objects.all().order_by('-updated_at')[:10]
        
        if not chats:
            logger.info("No chats found in the database")
            return
        
        logger.info("\n=== Recent Chats ===")
        for chat in chats:
            appointment = chat.appointment
            logger.info(f"Chat ID: {chat.firebase_chat_id}")
            logger.info(f"  Appointment ID: {appointment.appointment_id}")
            logger.info(f"  Doctor: {appointment.doctor.full_name} (ID: {appointment.doctor.id})")
            logger.info(f"  Patient ID: {appointment.patient_id}")
            logger.info(f"  Patient Name: {appointment.patient_name}")
            logger.info(f"  Updated: {chat.updated_at}")
            logger.info("---")
        
    except Exception as e:
        logger.error(f"Error listing chats: {e}")

def main():
    """Main function to parse arguments and run the test"""
    parser = argparse.ArgumentParser(description='Send a test chat message from a doctor to a patient')
    
    # Create a mutually exclusive group for chat_id or appointment_id
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--chat-id', help='Firebase chat ID')
    group.add_argument('--appointment-id', help='Appointment ID')
    
    parser.add_argument('--doctor-id', help='Doctor ID (optional, will use appointment\'s doctor if not provided)')
    parser.add_argument('--message', help='Message text to send')
    parser.add_argument('--list-chats', action='store_true', help='List available chats and exit')
    
    args = parser.parse_args()
    
    if args.list_chats:
        list_available_chats()
        return
    
    if not args.chat_id and not args.appointment_id:
        logger.error("Either --chat-id or --appointment-id must be provided")
        parser.print_help()
        return
    
    send_test_message(
        chat_id=args.chat_id,
        appointment_id=args.appointment_id,
        doctor_id=args.doctor_id,
        message=args.message
    )

if __name__ == "__main__":
    main()