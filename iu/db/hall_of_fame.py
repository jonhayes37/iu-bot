"""Database operations for Hall of Fame nominations."""

import os
import sqlite3
import logging
from utils.end_of_year import get_current_award_year

logger = logging.getLogger('iu-bot')

DB_PATH_HALL_OF_FAME = os.getenv('DB_PATH_HALL_OF_FAME')

def save_hof_nomination(user_id: int, username: str, text: str) -> int:
    """Saves or updates a user's Hall of Fame nomination."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HALL_OF_FAME) as conn:
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
        with sqlite3.connect(DB_PATH_HALL_OF_FAME) as conn:
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
        with sqlite3.connect(DB_PATH_HALL_OF_FAME) as conn:
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

def set_hof_final_nominees(nominees: list[str]) -> int:
    """
    Wipes any existing final nominees for the HoF (for the current year)
    and inserts the new vetted list.
    """
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HALL_OF_FAME) as conn:
            cursor = conn.cursor()

            # Clear out the old list for the current year
            cursor.execute("""
                DELETE FROM hof_official_nominees
                WHERE award_year = ?
            """, (award_year,))

            # Insert the new pipe-separated list
            cursor.executemany("""
                INSERT INTO hof_official_nominees (award_year, nominee_name)
                VALUES (?, ?)
            """, [(award_year, name) for name in nominees])

            conn.commit()

        return award_year
    except Exception as ex:
        logger.error("Failed to set HoF final nominees: %s", ex)
        raise

def get_official_hof_nominees() -> list[str]:
    """Fetches the vetted list of final nominees to populate the UI dropdowns."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HALL_OF_FAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT nominee_name FROM hof_official_nominees 
                WHERE award_year = ? ORDER BY nominee_name
            """, (award_year,))
            return [row[0] for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Failed to fetch official HoF nominees: %s", ex)
        return []

def save_hof_vote(user_id: int, first: str, second: str, third: str) -> int:
    """Saves or updates a user's ranked HoF ballot."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HALL_OF_FAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO hall_of_fame_votes 
                (user_id, award_year, first_choice, second_choice, third_choice)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, award_year, first, second, third))
            conn.commit()
        return award_year
    except Exception as ex:
        logger.error("Failed to save HoF vote for %s: %s", user_id, ex)
        raise

def get_user_hof_vote(user_id: int) -> dict | None:
    """Fetches a user's existing vote to prepopulate the UI."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HALL_OF_FAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT first_choice, second_choice, third_choice 
                FROM hall_of_fame_votes 
                WHERE user_id = ? AND award_year = ?
            """, (user_id, award_year))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as ex:
        logger.error("Failed to fetch HoF vote for %s: %s", user_id, ex)
        return None
