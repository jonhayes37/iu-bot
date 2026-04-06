"""Helpers for end of year festivities"""

from datetime import datetime
import zoneinfo

def get_current_award_year() -> int:
    """Calculates the award year based on the Dec 1 - Nov 30 offset."""
    est_zone = zoneinfo.ZoneInfo("America/Toronto")
    now = datetime.now(est_zone)
    return now.year + 1 if now.month == 12 else now.year
