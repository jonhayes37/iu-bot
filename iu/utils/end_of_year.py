"""Helpers for end of year festivities"""

from datetime import datetime
import zoneinfo

# The awards year turns over at midnight on December 1 in the server's time zone
AWARDS_TIME_ZONE = zoneinfo.ZoneInfo("America/Toronto")


def award_year_for(moment: datetime) -> int:
    """
    The awards year a timezone-aware moment belongs to: December 1 to November 30, counted in Toronto
    time, so December belongs to the next year's awards.
    """
    local = moment.astimezone(AWARDS_TIME_ZONE)
    return local.year + 1 if local.month == 12 else local.year


def get_current_award_year() -> int:
    """The awards year it is now."""
    return award_year_for(datetime.now(AWARDS_TIME_ZONE))
