"""Database operations for core bot management."""

import enum
from dataclasses import dataclass
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


class EndOfYearPostKind(enum.StrEnum):
    """The end of year posts that carry buttons."""
    SUGGESTIONS = 'suggestions'
    NOMINATIONS = 'nominations'
    VOTING = 'voting'


@dataclass(frozen=True)
class EndOfYearPost:
    """Where an end of year post with buttons was sent."""
    kind: EndOfYearPostKind
    channel_id: int
    message_id: int


def record_end_of_year_post(award_year: int, kind: EndOfYearPostKind, channel_id: int, message_id: int) -> None:
    """Remembers a posted end of year hub so it can be closed later."""
    with db_connection(Database.BOT) as conn:
        conn.execute("""
            INSERT OR IGNORE INTO end_of_year_posts (message_id, channel_id, award_year, kind)
            VALUES (?, ?, ?, ?)
        """, (message_id, channel_id, award_year, str(kind)))

def get_end_of_year_posts(award_year: int) -> list[EndOfYearPost]:
    """The year's end of year hubs, oldest first."""
    with db_connection(Database.BOT) as conn:
        rows = conn.execute("""
            SELECT kind, channel_id, message_id FROM end_of_year_posts
            WHERE award_year = ? ORDER BY posted_at, message_id
        """, (award_year,)).fetchall()
        return [EndOfYearPost(EndOfYearPostKind(kind), channel_id, message_id) for kind, channel_id, message_id in rows]

def close_end_of_year(award_year: int) -> bool:
    """Closes the year's festivities. Returns False if they were already closed."""
    with db_connection(Database.BOT) as conn:
        cursor = conn.execute("INSERT OR IGNORE INTO end_of_year_closed (award_year) VALUES (?)", (award_year,))
        return cursor.rowcount == 1

def is_end_of_year_closed(award_year: int) -> bool:
    """True once the year's festivities have been closed with /end-of-year-close."""
    with db_connection(Database.BOT) as conn:
        row = conn.execute("SELECT 1 FROM end_of_year_closed WHERE award_year = ?", (award_year,)).fetchone()
        return row is not None
