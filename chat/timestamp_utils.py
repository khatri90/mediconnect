"""
Utilities for handling timestamps in the chat application
"""

import logging
from datetime import datetime
import dateutil.parser

logger = logging.getLogger(__name__)

def parse_timestamp(timestamp_str, default=None):
    """
    Parse an ISO 8601 timestamp string to a datetime object
    
    Args:
        timestamp_str (str): The timestamp string to parse
        default: Value to return if parsing fails
        
    Returns:
        datetime or default: The parsed datetime or default value if parsing fails
    """
    if not timestamp_str:
        return default
    
    try:
        return dateutil.parser.parse(timestamp_str)
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid timestamp format: {timestamp_str}, error: {e}")
        return default

def format_timestamp(dt):
    """
    Format a datetime object as an ISO 8601 string
    
    Args:
        dt (datetime): The datetime object to format
        
    Returns:
        str: The formatted timestamp string
    """
    if not dt:
        return datetime.now().isoformat()
    
    if isinstance(dt, datetime):
        return dt.isoformat()
    
    return str(dt)

def now():
    """
    Get the current datetime as an ISO 8601 string
    
    Returns:
        str: The current timestamp as an ISO 8601 string
    """
    return datetime.now().isoformat()