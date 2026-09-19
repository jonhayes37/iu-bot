"""Database operations for core bot management."""

import logging
from datetime import datetime, timezone, timedelta
from config import Database
from db.connection import db_connection

logger = logging.getLogger('iu-bot')

def save_bot_status_db(status_text: str, days: int) -> bool:
    """Saves a new status to the ledger."""
    try:
        with db_connection(Database.BOT) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO statuses (status_text, max_duration_days)
                VALUES (?, ?)
            """, (status_text, days))
            conn.commit()
            return True
    except Exception as ex:
        logger.error("Failed to save bot status: %s", ex)
        return False

def get_active_bot_status_db() -> str | None:
    """
    Fetches the most recent status.
    Returns None if there are no statuses or if the latest one has expired.
    """
    try:
        with db_connection(Database.BOT, row_factory=True) as conn:
            cursor = conn.cursor()

            # Grab the absolute latest status
            cursor.execute("""
                SELECT status_text, max_duration_days, created_at
                FROM statuses
                ORDER BY created_at DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            if not row:
                return None

            # SQLite stores CURRENT_TIMESTAMP as UTC string: "YYYY-MM-DD HH:MM:SS"
            # We append +00:00 to make it timezone-aware in Python
            created_at_str = row['created_at'] + "+00:00"
            created_at = datetime.fromisoformat(created_at_str)

            # Check expiration
            expiration_date = created_at + timedelta(days=row['max_duration_days'])
            now = datetime.now(timezone.utc)

            if now <= expiration_date:
                return row['status_text']

            # The latest status has expired
            return None

    except Exception as ex:
        logger.error("Failed to fetch active bot status: %s", ex)
        return None
