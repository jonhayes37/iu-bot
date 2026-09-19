"""Database logic for list events and submissions."""

import logging
import sqlite3
from config import Database
from db.connection import db_connection

logger = logging.getLogger('iu-bot')

def create_new_event(event_id: str, event_name: str, expected_count: int, placeholder: str) -> bool:
    """Inserts a new list event into the database."""
    try:
        with db_connection(Database.LISTS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO list_events (event_id, event_name, expected_count, placeholder_text, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (event_id, event_name, expected_count, placeholder))
            return True
    except sqlite3.IntegrityError:
        logger.error("Event ID '%s' already exists!", event_id)
        return False
    except Exception as ex:
        logger.error("Failed to create list event '%s': %s", event_id, ex)
        return False

def get_event_details(event_id: str) -> dict | None:
    """Fetches the configuration for a specific event."""
    try:
        with db_connection(Database.LISTS, row_factory=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM list_events WHERE event_id = ?", (event_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as ex:
        logger.error("Failed to fetch event details for '%s': %s", event_id, ex)
        return None

def close_event(event_id: str) -> bool:
    """Marks an event as inactive so no more submissions are accepted."""
    try:
        with db_connection(Database.LISTS) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE list_events SET is_active = 0 WHERE event_id = ?", (event_id,))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Failed to close event '%s': %s", event_id, ex)
        return False

def save_submission(event_id: str, user_id: int, username: str, raw_text: str, cleaned_text: str, urls: str) -> bool:
    """Saves or updates a user's list submission."""
    try:
        with db_connection(Database.LISTS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO list_submissions
                (event_id, user_id, username, raw_text, cleaned_text, extracted_urls)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (event_id, user_id, username, raw_text, cleaned_text, urls))
            return True
    except Exception as ex:
        logger.error("Failed to save submission for user %s: %s", user_id, ex)
        return False

def get_all_submissions(event_id: str) -> list[dict]:
    """Fetches all submissions for an event to be exported."""
    try:
        with db_connection(Database.LISTS, row_factory=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM list_submissions WHERE event_id = ?", (event_id,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Failed to fetch submissions for event '%s': %s", event_id, ex)
        return []

def set_event_message_id(event_id: str, message_id: str) -> bool:
    """Links the Discord message ID to the event for easy closing later."""
    try:
        with db_connection(Database.LISTS) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE list_events SET message_id = ? WHERE event_id = ?", (message_id, event_id))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Failed to set message ID for event '%s': %s", event_id, ex)
        return False

def get_user_submission(event_id: str, user_id: int) -> str | None:
    """Fetches a user's previous raw submission text if it exists."""
    try:
        with db_connection(Database.LISTS) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT raw_text FROM list_submissions WHERE event_id = ? AND user_id = ?",
                           (event_id, user_id))
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as ex:
        logger.error("Failed to fetch submission for user %s: %s", user_id, ex)
        return None
