# doctors/appointment_service.py

import logging
from datetime import datetime, timedelta
from django.utils import timezone
from .models import Appointment
from .zoom_service import ZoomService

logger = logging.getLogger(__name__)

class AppointmentService:
    """Service class for managing appointments"""
    
    def __init__(self):
        self.zoom_service = ZoomService()
    
    def create_appointment(self, appointment_data):
        """
        Create an appointment with Zoom meeting integration
        
        Args:
            appointment_data (dict): Appointment data including doctor, patient, date, time, etc.
            
        Returns:
            Appointment: Created appointment object with Zoom meeting details
        """
        try:
            # Create appointment first (without saving)
            appointment = Appointment(**appointment_data)
            
            # Convert appointment date and time to UTC datetime
            appointment_datetime = datetime.combine(
                appointment.appointment_date,
                appointment.start_time
            )
            
            # Calculate the duration in minutes
            end_datetime = datetime.combine(
                appointment.appointment_date,
                appointment.end_time
            )
            duration_minutes = int((end_datetime - appointment_datetime).total_seconds() / 60)
            
            # Create Zoom meeting for the appointment
            meeting_topic = f"Medical Appointment with {appointment.doctor.full_name} for {appointment.patient_name}"
            
            meeting_details = self.zoom_service.create_meeting(
                topic=meeting_topic,
                start_time=appointment_datetime,
                duration=duration_minutes,
                doctor_email=appointment.doctor.email,
                patient_email=appointment.patient_email
            )
            
            # Add Zoom meeting details to the appointment
            appointment.zoom_meeting_id = meeting_details['meeting_id']
            appointment.zoom_meeting_url = meeting_details['join_url']
            appointment.zoom_meeting_password = meeting_details['password']
            appointment.zoom_meeting_status = 'scheduled'
            appointment.zoom_meeting_duration = duration_minutes
            
            # Save the appointment
            appointment.save()
            
            logger.info(f"Created appointment with Zoom meeting: {appointment.appointment_id}")
            return appointment
            
        except Exception as e:
            logger.error(f"Error creating appointment with Zoom meeting: {str(e)}")
            raise
    
    def update_appointment(self, appointment_id, update_data):
        """
        Update an appointment and its Zoom meeting details
        
        Args:
            appointment_id (str): The appointment ID
            update_data (dict): Updated appointment data
            
        Returns:
            Appointment: Updated appointment object
        """
        try:
            appointment = Appointment.objects.get(appointment_id=appointment_id)
            
            # Check if date or time has changed
            date_changed = 'appointment_date' in update_data and update_data['appointment_date'] != appointment.appointment_date
            start_time_changed = 'start_time' in update_data and update_data['start_time'] != appointment.start_time
            end_time_changed = 'end_time' in update_data and update_data['end_time'] != appointment.end_time
            
            # Update appointment fields
            for field, value in update_data.items():
                setattr(appointment, field, value)
            
            # If date or time has changed and there's a Zoom meeting, update it
            if (date_changed or start_time_changed or end_time_changed) and appointment.zoom_meeting_id:
                # Convert appointment date and time to UTC datetime
                appointment_datetime = datetime.combine(
                    appointment.appointment_date,
                    appointment.start_time
                )
                
                # Calculate the duration in minutes
                end_datetime = datetime.combine(
                    appointment.appointment_date,
                    appointment.end_time
                )
                duration_minutes = int((end_datetime - appointment_datetime).total_seconds() / 60)
                
                # Update Zoom meeting
                self.zoom_service.update_meeting(
                    meeting_id=appointment.zoom_meeting_id,
                    start_time=appointment_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
                    duration=duration_minutes
                )
                
                appointment.zoom_meeting_duration = duration_minutes
            
            # Save the updated appointment
            appointment.save()
            
            logger.info(f"Updated appointment: {appointment.appointment_id}")
            return appointment
            
        except Appointment.DoesNotExist:
            logger.error(f"Appointment not found: {appointment_id}")
            raise
        except Exception as e:
            logger.error(f"Error updating appointment: {str(e)}")
            raise
    
    def cancel_appointment(self, appointment_id, reason=None):
        """
        Cancel an appointment and its Zoom meeting
        
        Args:
            appointment_id (str): The appointment ID
            reason (str, optional): Cancellation reason
            
        Returns:
            Appointment: Cancelled appointment object
        """
        try:
            appointment = Appointment.objects.get(appointment_id=appointment_id)
            
            # Update appointment status
            appointment.status = 'cancelled'
            
            # Add cancellation reason if provided
            if reason:
                if appointment.admin_notes:
                    appointment.admin_notes += f"\nCancellation reason: {reason}"
                else:
                    appointment.admin_notes = f"Cancellation reason: {reason}"
            
            # If there's a Zoom meeting, delete it
            if appointment.zoom_meeting_id:
                try:
                    self.zoom_service.delete_meeting(appointment.zoom_meeting_id)
                    appointment.zoom_meeting_status = 'cancelled'
                except Exception as e:
                    logger.error(f"Error deleting Zoom meeting: {str(e)}")
            
            # Save the cancelled appointment
            appointment.save()
            
            logger.info(f"Cancelled appointment: {appointment.appointment_id}")
            return appointment
            
        except Appointment.DoesNotExist:
            logger.error(f"Appointment not found: {appointment_id}")
            raise
        except Exception as e:
            logger.error(f"Error cancelling appointment: {str(e)}")
            raise
    
    def track_meeting_attendance(self, meeting_id, host_joined=None, client_joined=None):
        """
        Track attendance for a Zoom meeting
        
        Args:
            meeting_id (str): Zoom meeting ID
            host_joined (bool, optional): Whether the host (doctor) joined
            client_joined (bool, optional): Whether the client (patient) joined
            
        Returns:
            Appointment: Updated appointment object
        """
        try:
            appointment = Appointment.objects.get(zoom_meeting_id=meeting_id)
            
            # Update attendance flags if provided
            if host_joined is not None:
                appointment.zoom_host_joined = host_joined
            
            if client_joined is not None:
                appointment.zoom_client_joined = client_joined
            
            # Update meeting status based on attendance
            if appointment.zoom_host_joined and appointment.zoom_client_joined:
                appointment.zoom_meeting_status = 'completed'
            elif appointment.zoom_host_joined or appointment.zoom_client_joined:
                # If at least one participant joined, mark as started
                appointment.zoom_meeting_status = 'started'
            
            # Save the appointment
            appointment.save()
            
            logger.info(f"Updated meeting attendance: {meeting_id}")
            return appointment
            
        except Appointment.DoesNotExist:
            logger.error(f"Appointment with Zoom meeting ID not found: {meeting_id}")
            raise
        except Exception as e:
            logger.error(f"Error tracking meeting attendance: {str(e)}")
            raise