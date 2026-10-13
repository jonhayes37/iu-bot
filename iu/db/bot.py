"""Database operations for core bot management."""

from datetime import datetime, timezone, timedelta
from config import Database
from db.connection import db_connection
from utils.timestamps import parse_db_timestamp

def save_bot_status_db(status_text: str, days: int) -> None:
    """Saves a new status to the ledger."""
    with db_connection(Database.BOT) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO statuses (status_text, max_duration_days)
            VALUES (?, ?)
        """, (status_text, days))

def get_active_bot_status_db() -> str | None:
    """
    Fetches the most recent status.
    Returns None if there are no statuses or if the latest one has expired.
    """
    with db_connection(Database.BOT, row_factory=True) as conn:
        cursor = conn.cursor()

        # Grab the absolute latest status
        cursor.execute("""
            SELECT status_text, max_duration_days, created_at
            FROM statuses
            ORDER BY created_at DESC, id DESC  -- created_at is to the second, so the newest row wins a tie
            LIMIT 1
        """)

        row = cursor.fetchone()
        if not row:
            return None

        created_at = parse_db_timestamp(row['created_at'])

        # Check expiration
        expiration_date = created_at + timedelta(days=row['max_duration_days'])
        now = datetime.now(timezone.utc)

        if now <= expiration_date:
            return row['status_text']

        # The latest status has expired
        return None

def was_event_notified_db(event_id: int) -> bool:
    """True if the reminder thread for this scheduled event has already been posted."""
    with db_connection(Database.BOT) as conn:
        row = conn.execute("SELECT 1 FROM notified_events WHERE event_id = ?", (event_id,)).fetchone()
        return row is not None

def mark_event_notified_db(event_id: int) -> None:
    """Records that the reminder thread for this scheduled event has been posted."""
    with db_connection(Database.BOT) as conn:
        conn.execute("INSERT OR IGNORE INTO notified_events (event_id) VALUES (?)", (event_id,))
