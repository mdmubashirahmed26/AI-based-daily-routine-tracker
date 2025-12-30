"""
Utility functions for the Routine Tracker
"""
from datetime import timedelta

def minutes_to_hhmm(minutes: int) -> str:
    """Convert minutes to HH:MM format"""
    if minutes < 0:
        return "00:00"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

def seconds_to_hhmmss(seconds: int) -> str:
    """Convert seconds to HH:MM:SS format"""
    if seconds < 0:
        return "00:00:00"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def format_timedelta(delta: timedelta) -> str:
    """Format timedelta to readable string"""
    total_seconds = int(delta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours}h {minutes}m"

def calculate_productivity(planned_minutes: int, completed_minutes: int) -> float:
    """Calculate productivity percentage"""
    if planned_minutes == 0:
        return 0.0
    return min(100.0, (completed_minutes / planned_minutes) * 100)
