"""Database operations for End of Year Top 25 submissions."""

from config import Database
from db.connection import db_connection
from utils.end_of_year import get_current_award_year

def save_top_songs(
    user_id: int, username: str,
    t25_raw: str, t25_clean: str, t25_urls: str,
    hms_raw: str, hms_clean: str, hms_urls: str
) -> int:
    """Saves or updates a user's Top 25 and Honorable Mentions."""
    award_year = get_current_award_year()
    with db_connection(Database.TOP_SONGS) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO eoy_top_songs
            (user_id, award_year, username, top_25_raw, top_25_clean, top_25_urls, hms_raw, hms_clean, hms_urls)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, award_year, username, t25_raw, t25_clean, t25_urls, hms_raw, hms_clean, hms_urls))
    return award_year

def get_user_top_songs(user_id: int) -> dict | None:
    """Fetches a user's existing Top 25 raw submission for the current year to pre-populate the modal."""
    award_year = get_current_award_year()
    with db_connection(Database.TOP_SONGS, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT top_25_raw, hms_raw
            FROM eoy_top_songs
            WHERE user_id = ? AND award_year = ?
        """, (user_id, award_year))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_top_songs() -> list[dict]:
    """Fetches all submissions for the current award year to be exported."""
    award_year = get_current_award_year()
    with db_connection(Database.TOP_SONGS, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM eoy_top_songs WHERE award_year = ?", (award_year,))
        return [dict(row) for row in cursor.fetchall()]
