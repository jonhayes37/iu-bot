"""Database operations for End of Year Top 25 submissions.

Every function takes the awards year it works on (the year of the hub or command that asked).
"""

from config import Database
from db.connection import db_connection

def save_top_songs(
    award_year: int, user_id: int, username: str,
    t25_raw: str, t25_clean: str, t25_urls: str,
    hms_raw: str, hms_clean: str, hms_urls: str
):
    """Saves or updates a user's Top 25 and Honorable Mentions."""
    with db_connection(Database.TOP_SONGS) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO eoy_top_songs
            (user_id, award_year, username, top_25_raw, top_25_clean, top_25_urls, hms_raw, hms_clean, hms_urls)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, award_year, username, t25_raw, t25_clean, t25_urls, hms_raw, hms_clean, hms_urls))

def get_user_top_songs(award_year: int, user_id: int) -> dict | None:
    """Fetches a user's existing Top 25 raw submission for the year to pre-populate the modal."""
    with db_connection(Database.TOP_SONGS, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT top_25_raw, hms_raw
            FROM eoy_top_songs
            WHERE user_id = ? AND award_year = ?
        """, (user_id, award_year))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_top_songs(award_year: int) -> list[dict]:
    """Fetches all submissions for the award year to be exported."""
    with db_connection(Database.TOP_SONGS, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM eoy_top_songs WHERE award_year = ?", (award_year,))
        return [dict(row) for row in cursor.fetchall()]
