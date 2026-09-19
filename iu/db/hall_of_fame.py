"""Database operations for Hall of Fame nominations."""

from config import Database
from db.connection import db_connection
from utils.end_of_year import get_current_award_year

def save_hof_nomination(user_id: int, username: str, text: str) -> int:
    """Saves or updates a user's Hall of Fame nomination."""
    award_year = get_current_award_year()
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO hall_of_fame_nominations
            (user_id, award_year, username, nomination_text)
            VALUES (?, ?, ?, ?)
        """, (user_id, award_year, username, text))
    return award_year

def get_all_hof_nominations() -> list[dict]:
    """Fetches all HoF submissions for the current award year to be exported."""
    award_year = get_current_award_year()
    with db_connection(Database.HALL_OF_FAME, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hall_of_fame_nominations WHERE award_year = ?", (award_year,))
        return [dict(row) for row in cursor.fetchall()]

def get_hof_nomination(user_id: int) -> str | None:
    """Fetches a user's existing Hall of Fame nomination for the current year."""
    award_year = get_current_award_year()
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nomination_text
            FROM hall_of_fame_nominations
            WHERE user_id = ? AND award_year = ?
        """, (user_id, award_year))
        row = cursor.fetchone()
        return row[0] if row else None

def set_hof_final_nominees(nominees: list[str]) -> int:
    """
    Wipes any existing final nominees for the HoF (for the current year)
    and inserts the new vetted list.
    """
    award_year = get_current_award_year()
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.cursor()

        # Clear out the old list for the current year
        cursor.execute("""
            DELETE FROM hof_official_nominees
            WHERE award_year = ?
        """, (award_year,))

        # Insert the new pipe-separated list
        cursor.executemany("""
            INSERT INTO hof_official_nominees (award_year, nominee_name)
            VALUES (?, ?)
        """, [(award_year, name) for name in nominees])


    return award_year

def get_official_hof_nominees() -> list[str]:
    """Fetches the vetted list of final nominees to populate the UI dropdowns."""
    award_year = get_current_award_year()
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nominee_name FROM hof_official_nominees
            WHERE award_year = ? ORDER BY nominee_name
        """, (award_year,))
        return [row[0] for row in cursor.fetchall()]

def save_hof_vote(user_id: int, first: str, second: str, third: str) -> int:
    """Saves or updates a user's ranked HoF ballot."""
    award_year = get_current_award_year()
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO hall_of_fame_votes
            (user_id, award_year, first_choice, second_choice, third_choice)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, award_year, first, second, third))
    return award_year

def get_user_hof_vote(user_id: int) -> dict | None:
    """Fetches a user's existing vote to prepopulate the UI."""
    award_year = get_current_award_year()
    with db_connection(Database.HALL_OF_FAME, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT first_choice, second_choice, third_choice
            FROM hall_of_fame_votes
            WHERE user_id = ? AND award_year = ?
        """, (user_id, award_year))
        row = cursor.fetchone()
        return dict(row) if row else None
