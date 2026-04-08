"""Database operations for End of Year Top 25 submissions."""

import os
import sqlite3
import logging
from datetime import datetime
import zoneinfo

logger = logging.getLogger('iu-bot')

DB_PATH_TOP_SONGS = os.getenv('DB_PATH_TOP_SONGS')

def get_current_award_year() -> int:
    """Calculates the award year based on the Dec 1 - Nov 30 offset."""
    est_zone = zoneinfo.ZoneInfo("America/Toronto")
    now = datetime.now(est_zone)
    return now.year + 1 if now.month == 12 else now.year

def save_top_songs(
    user_id: int, username: str,
    t25_raw: str, t25_clean: str, t25_urls: str,
    hms_raw: str, hms_clean: str, hms_urls: str
) -> int:
    """Saves or updates a user's Top 25 and Honorable Mentions."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_TOP_SONGS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO eoy_top_songs 
                (user_id, award_year, username, top_25_raw, top_25_clean, top_25_urls, hms_raw, hms_clean, hms_urls)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, award_year, username, t25_raw, t25_clean, t25_urls, hms_raw, hms_clean, hms_urls))
            conn.commit()
        return award_year
    except Exception as ex:
        logger.error("Failed to save Top 25 for %s: %s", user_id, ex)
        raise

def get_user_top_songs(user_id: int) -> dict | None:
    """Fetches a user's existing Top 25 raw submission for the current year to pre-populate the modal."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_TOP_SONGS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT top_25_raw, hms_raw 
                FROM eoy_top_songs 
                WHERE user_id = ? AND award_year = ?
            """, (user_id, award_year))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as ex:
        logger.error("Failed to fetch Top 25 for %s: %s", user_id, ex)
        return None

def get_all_top_songs() -> list[dict]:
    """Fetches all submissions for the current award year to be exported."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_TOP_SONGS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eoy_top_songs WHERE award_year = ?", (award_year,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Failed to fetch all Top 25 for year %s: %s", award_year, ex)
        return []
