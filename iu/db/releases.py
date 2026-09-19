"""Triggers related to parsing new releases from messages and storing them in the database."""

import enum
import sqlite3
import logging
from datetime import datetime
from config import Database
from db.connection import db_connection

logger = logging.getLogger('iu-bot')

class AddResult(enum.Enum):
    """Outcome of recording a posted release."""
    ADDED = "added"          # new release, still needs to go on the playlist
    PENDING = "pending"      # seen before but never made it onto the playlist, so try again
    DUPLICATE = "duplicate"  # already handled
    ERROR = "error"

def add_new_release(video_id: str, original_url: str, message_id: str, msg_time: datetime) -> AddResult:
    """
    Records a parsed YouTube release. If the video was recorded earlier but never reached the
    playlist (for example the YouTube quota ran out), returns PENDING so the caller retries it.
    """
    try:
        with db_connection(Database.RELEASES) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO new_releases (video_id, original_url, message_id, timestamp)
                VALUES (?, ?, ?, ?)
            """, (video_id, original_url, message_id, msg_time.isoformat()))

            conn.commit()
            return AddResult.ADDED

    except sqlite3.IntegrityError:
        # The UNIQUE constraint caught a duplicate video_id or message_id
        return _classify_existing_release(video_id)
    except Exception as ex:
        logger.error("CRITICAL: Database error inserting release %s: %s", video_id, ex)
        return AddResult.ERROR

def _classify_existing_release(video_id: str) -> AddResult:
    """For a video that is already recorded: has it reached the playlist yet?"""
    try:
        with db_connection(Database.RELEASES) as conn:
            row = conn.execute("SELECT processed FROM new_releases WHERE video_id = ?", (video_id,)).fetchone()
    except Exception as ex:
        logger.error("Database error looking up release %s: %s", video_id, ex)
        return AddResult.ERROR

    if row is not None and not row[0]:
        logger.info("Release %s was recorded earlier but is not on the playlist yet; retrying.", video_id)
        return AddResult.PENDING

    logger.debug("Duplicate video_id or message_id ignored: %s", video_id)
    return AddResult.DUPLICATE

def mark_release_processed(video_id: str):
    """Marks a video as successfully added to YouTube so it isn't processed again."""
    with db_connection(Database.RELEASES) as conn:
        conn.execute("UPDATE new_releases SET processed = 1 WHERE video_id = ?", (video_id,))
        conn.commit()

def get_playlist_id_for_year(year: int) -> str | None:
    """Checks the database to see if a playlist for the target year already exists."""
    with db_connection(Database.RELEASES) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT playlist_id FROM youtube_playlists WHERE year = ?", (year,))
        row = cursor.fetchone()
        return row[0] if row else None

def save_new_playlist(year: int, playlist_id: str):
    """Saves a newly created YouTube playlist ID to the database."""
    with db_connection(Database.RELEASES) as conn:
        conn.execute(
            "INSERT INTO youtube_playlists (year, playlist_id) VALUES (?, ?)",
            (year, playlist_id)
        )
        conn.commit()
