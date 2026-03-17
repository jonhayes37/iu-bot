"""Database logic for list events and submissions."""

import logging
import os
import sqlite3

logger = logging.getLogger('iu-bot')

DB_PATH_LISTS = os.getenv('DB_PATH_LISTS')

def create_new_event(event_id: str, event_name: str, expected_count: int, placeholder: str) -> bool:
    """Inserts a new list event into the database."""
    if not DB_PATH_LISTS:
        logger.error("DB_PATH_LISTS environment variable not set! Cannot create new event.")
        return False

    try:
        with sqlite3.connect(DB_PATH_LISTS) as conn:
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
    if not DB_PATH_LISTS:
        logger.error("DB_PATH_LISTS environment variable not set! Cannot create new event.")
        return None

    try:
        with sqlite3.connect(DB_PATH_LISTS) as conn:
            conn.row_factory = sqlite3.Row # Necessary to return dicts instead of tuples
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM list_events WHERE event_id = ?", (event_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as ex:
        logger.error("Failed to fetch event details for '%s': %s", event_id, ex)
        return None

def close_event(event_id: str) -> bool:
    """Marks an event as inactive so no more submissions are accepted."""
    if not DB_PATH_LISTS:
        logger.error("DB_PATH_LISTS environment variable not set! Cannot create new event.")
        return False

    try:
        with sqlite3.connect(DB_PATH_LISTS) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE list_events SET is_active = 0 WHERE event_id = ?", (event_id,))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Failed to close event '%s': %s", event_id, ex)
        return False

def save_submission(event_id: str, user_id: int, raw_text: str, cleaned_text: str, urls: str) -> bool:
    """Saves or updates a user's list submission."""
    if not DB_PATH_LISTS:
        logger.error("DB_PATH_LISTS environment variable not set! Cannot create new event.")
        return False

    try:
        with sqlite3.connect(DB_PATH_LISTS) as conn:
            cursor = conn.cursor()
            # Because we set UNIQUE(event_id, user_id) in the schema,
            # this will flawlessly overwrite their old list if they submit again!
            cursor.execute("""
                INSERT OR REPLACE INTO list_submissions 
                (event_id, user_id, raw_text, cleaned_text, extracted_urls)
                VALUES (?, ?, ?, ?, ?)
            """, (event_id, user_id, raw_text, cleaned_text, urls))
            return True
    except Exception as ex:
        logger.error("Failed to save submission for user %s on event '%s': %s", user_id, event_id, ex)
        return False

def set_event_message_id(event_id: str, message_id: str) -> bool:
    """Links the Discord message ID to the event for easy closing later."""
    if not DB_PATH_LISTS:
        logger.error("DB_PATH_LISTS environment variable not set! Cannot set event message ID.")
        return False
    try:
        with sqlite3.connect(DB_PATH_LISTS) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE list_events SET message_id = ? WHERE event_id = ?", (message_id, event_id))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Failed to set message ID for event '%s': %s", event_id, ex)
        return False

def get_user_submission(event_id: str, user_id: int) -> str | None:
    """Fetches a user's previous raw submission text if it exists."""
    if not DB_PATH_LISTS:
        logger.error("DB_PATH_LISTS environment variable not set! Cannot fetch user submission.")
        return None
    try:
        with sqlite3.connect(DB_PATH_LISTS) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT raw_text FROM list_submissions WHERE event_id = ? AND user_id = ?",
                           (event_id, user_id))
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as ex:
        logger.error("Failed to fetch submission for user %s: %s", user_id, ex)
        return None
