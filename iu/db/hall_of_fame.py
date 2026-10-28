"""Database operations for Hall of Fame nominations.

Every function takes the awards year it works on (the year of the hub or command that asked).
"""

from config import Database
from db.connection import db_connection

def save_hof_nomination(award_year: int, user_id: int, username: str, text: str):
    """Saves or updates a user's Hall of Fame nomination."""
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO hall_of_fame_nominations
            (user_id, award_year, username, nomination_text)
            VALUES (?, ?, ?, ?)
        """, (user_id, award_year, username, text))

def get_all_hof_nominations(award_year: int) -> list[dict]:
    """Fetches all HoF submissions for the award year to be exported."""
    with db_connection(Database.HALL_OF_FAME, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hall_of_fame_nominations WHERE award_year = ?", (award_year,))
        return [dict(row) for row in cursor.fetchall()]

def get_hof_nomination(award_year: int, user_id: int) -> str | None:
    """Fetches a user's existing Hall of Fame nomination for the year."""
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nomination_text
            FROM hall_of_fame_nominations
            WHERE user_id = ? AND award_year = ?
        """, (user_id, award_year))
        row = cursor.fetchone()
        return row[0] if row else None

def set_hof_final_nominees(award_year: int, nominees: list[str]):
    """
    Wipes any existing final nominees for the HoF (for the year)
    and inserts the new vetted list.
    """
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.cursor()

        # Clear out the old list for the year
        cursor.execute("""
            DELETE FROM hof_official_nominees
            WHERE award_year = ?
        """, (award_year,))

        # Insert the new pipe-separated list
        cursor.executemany("""
            INSERT INTO hof_official_nominees (award_year, nominee_name)
            VALUES (?, ?)
        """, [(award_year, name) for name in nominees])

def get_official_hof_nominees(award_year: int) -> list[str]:
    """Fetches the vetted list of final nominees to populate the UI dropdowns."""
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nominee_name FROM hof_official_nominees
            WHERE award_year = ? ORDER BY nominee_name
        """, (award_year,))
        return [row[0] for row in cursor.fetchall()]

def save_hof_vote(award_year: int, user_id: int, first: str, second: str, third: str):
    """Saves or updates a user's ranked HoF ballot."""
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO hall_of_fame_votes
            (user_id, award_year, first_choice, second_choice, third_choice)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, award_year, first, second, third))

def get_user_hof_vote(award_year: int, user_id: int) -> dict | None:
    """Fetches a user's existing vote to prepopulate the UI."""
    with db_connection(Database.HALL_OF_FAME, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT first_choice, second_choice, third_choice
            FROM hall_of_fame_votes
            WHERE user_id = ? AND award_year = ?
        """, (user_id, award_year))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_hof_ballots(award_year: int) -> list[tuple[str, str, str]]:
    """Every (1st, 2nd, 3rd choice) Hall of Fame ballot cast for the year."""
    with db_connection(Database.HALL_OF_FAME) as conn:
        rows = conn.execute("""
            SELECT first_choice, second_choice, third_choice
            FROM hall_of_fame_votes
            WHERE award_year = ?
        """, (award_year,)).fetchall()
        return [tuple(row) for row in rows]
