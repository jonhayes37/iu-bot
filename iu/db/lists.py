"""Database logic for list events and submissions."""

import enum
import sqlite3
from config import Database
from db.connection import db_connection
from db.merch import use_up_item

class SaveOutcome(enum.Enum):
    """Outcome of saving a list submission."""
    SAVED = "saved"
    ITEM_MISSING = "item_missing"  # a perk was required and the user doesn't have one; nothing was saved

def create_new_event(event_id: str, event_name: str, expected_count: int, placeholder: str) -> bool:
    """Inserts a new list event into the database. Returns False if that event ID already exists."""
    try:
        with db_connection(Database.LISTS) as conn:
            conn.execute("""
                INSERT INTO list_events (event_id, event_name, expected_count, placeholder_text, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (event_id, event_name, expected_count, placeholder))
            return True
    except sqlite3.IntegrityError:
        return False

def get_event_details(event_id: str) -> dict | None:
    """Fetches the configuration for a specific event."""
    with db_connection(Database.LISTS, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM list_events WHERE event_id = ?", (event_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def close_event(event_id: str) -> bool:
    """Marks an event as inactive so no more submissions are accepted."""
    with db_connection(Database.LISTS) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE list_events SET is_active = 0 WHERE event_id = ?", (event_id,))
        return cursor.rowcount > 0

def save_submission(event_id: str, user_id: int, username: str, raw_text: str, cleaned_text: str, urls: str,
                    use_item: str | None = None) -> SaveOutcome:
    """
    Saves or updates a user's list submission.

    If use_item is given (the code of a Merch Booth perk), one of that item is used up in the same
    transaction, with the merch database attached. The list and the item change together or not at
    all: a failed save can't cost the user their perk, and a missing perk saves nothing.
    """
    with db_connection(Database.LISTS, attach=(Database.MERCH,) if use_item else ()) as conn:
        if use_item:
            # Take the write lock on both databases up front, so nothing else can change the item first
            conn.execute("BEGIN IMMEDIATE")
            if not use_up_item(conn, user_id, use_item, schema="merch."):
                return SaveOutcome.ITEM_MISSING

        conn.execute("""
            INSERT OR REPLACE INTO list_submissions
            (event_id, user_id, username, raw_text, cleaned_text, extracted_urls)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (event_id, user_id, username, raw_text, cleaned_text, urls))
        return SaveOutcome.SAVED

def get_all_submissions(event_id: str) -> list[dict]:
    """Fetches all submissions for an event to be exported."""
    with db_connection(Database.LISTS, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM list_submissions WHERE event_id = ?", (event_id,))
        return [dict(row) for row in cursor.fetchall()]

def set_event_message_id(event_id: str, message_id: str) -> bool:
    """Links the Discord message ID to the event for easy closing later."""
    with db_connection(Database.LISTS) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE list_events SET message_id = ? WHERE event_id = ?", (message_id, event_id))
        return cursor.rowcount > 0

def get_user_submission(event_id: str, user_id: int) -> str | None:
    """Fetches a user's previous raw submission text if it exists."""
    with db_connection(Database.LISTS) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT raw_text FROM list_submissions WHERE event_id = ? AND user_id = ?",
                       (event_id, user_id))
        row = cursor.fetchone()
        return row[0] if row else None
