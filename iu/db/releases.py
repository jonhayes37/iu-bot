"""Triggers related to parsing new releases from messages and storing them in the database."""

import sqlite3
import logging
from datetime import datetime
from config import Database
from db.connection import db_connection

logger = logging.getLogger('iu-bot')

def add_new_release(video_id: str, original_url: str, message_id: str, msg_time: datetime) -> bool:
    """Inserts a parsed YouTube release into the database. Returns True if successful, False if it was a duplicate."""
    try:
        with db_connection(Database.RELEASES) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO new_releases (video_id, original_url, message_id, timestamp)
                VALUES (?, ?, ?, ?)
            """, (video_id, original_url, message_id, msg_time.isoformat()))

            conn.commit()
            return True

    except sqlite3.IntegrityError:
        # The UNIQUE constraint in your schema caught a duplicate video_id or message_id
        logger.debug("Duplicate video_id or message_id ignored: %s", video_id)
        return False
    except Exception as ex:
        # This will now show up in your Unraid logs if something breaks!
        logger.error("CRITICAL: Database error inserting release %s: %s", video_id, ex)
        return False

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
