"""Database operations for Hall of Fame nominations."""

import os
import sqlite3
import logging
from utils.end_of_year import get_current_award_year

logger = logging.getLogger('iu-bot')

DB_PATH_HOF_NOMINATIONS = os.getenv('DB_PATH_HOF_NOMINATIONS')

# db/hall_of_fame_nominations.py (Update these functions)

def save_hof_nomination(user_id: int, username: str, text: str) -> int:
    """Saves or updates a user's Hall of Fame nomination."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HOF_NOMINATIONS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO hall_of_fame_nominations 
                (user_id, award_year, username, nomination_text)
                VALUES (?, ?, ?, ?)
            """, (user_id, award_year, username, text))
            conn.commit()
        return award_year
    except Exception as ex:
        logger.error("Failed to save HoF nomination for %s: %s", user_id, ex)
        raise

def get_all_hof_nominations() -> list[dict]:
    """Fetches all HoF submissions for the current award year to be exported."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HOF_NOMINATIONS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hall_of_fame_nominations WHERE award_year = ?", (award_year,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Failed to fetch all HoF nominations for year %s: %s", award_year, ex)
        return []

def get_hof_nomination(user_id: int) -> str | None:
    """Fetches a user's existing Hall of Fame nomination for the current year."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HOF_NOMINATIONS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT nomination_text 
                FROM hall_of_fame_nominations 
                WHERE user_id = ? AND award_year = ?
            """, (user_id, award_year))
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as ex:
        logger.error("Failed to fetch HoF nomination for %s: %s", user_id, ex)
        return None
