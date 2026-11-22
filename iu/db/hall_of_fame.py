"""Database operations for Hall of Fame nominations, and the record of who has been inducted.

Every nomination and voting function takes the awards year it works on (the year of the hub or command
that asked).
"""

from dataclasses import dataclass

from config import Database
from db.connection import db_connection


@dataclass(frozen=True)
class Inductee:
    """Someone in the Hall of Fame, or given a lifetime achievement award."""
    name: str
    year_inducted: int

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


# The two tables have the same columns. The table name can't be a bound parameter, so it always comes
# from these constants, never from user input.
_HALL_OF_FAMERS = "hall_of_famers"
_LIFETIME_ACHIEVERS = "lifetime_achievers"


def _induct(table: str, name: str, year: int) -> bool:
    """Adds `name`; False (and nothing changes) when they are already in, in any capitalisation."""
    with db_connection(Database.HALL_OF_FAME) as conn:
        cursor = conn.execute(f"""
            INSERT INTO {table} (name, year_inducted) VALUES (?, ?)
            ON CONFLICT (name) DO NOTHING
        """, (name, year))
        return cursor.rowcount == 1


def _find(table: str, name: str) -> Inductee | None:
    with db_connection(Database.HALL_OF_FAME) as conn:
        row = conn.execute(f"SELECT name, year_inducted FROM {table} WHERE name = ?", (name,)).fetchone()
        return Inductee(*row) if row else None


def _all(table: str) -> list[Inductee]:
    with db_connection(Database.HALL_OF_FAME) as conn:
        rows = conn.execute(f"SELECT name, year_inducted FROM {table} ORDER BY year_inducted, name").fetchall()
        return [Inductee(*row) for row in rows]


def add_hall_of_famer(name: str, year: int) -> bool:
    """Inducts `name` into the Hall of Fame in `year`. False if they're already in it (ignoring case)."""
    return _induct(_HALL_OF_FAMERS, name, year)


def find_hall_of_famer(name: str) -> Inductee | None:
    """The Hall of Famer with this name (ignoring case), or None."""
    return _find(_HALL_OF_FAMERS, name)


def get_hall_of_famers() -> list[Inductee]:
    """Everyone in the Hall of Fame, oldest induction first, then by name."""
    return _all(_HALL_OF_FAMERS)


def add_lifetime_achiever(name: str, year: int) -> bool:
    """Gives `name` the lifetime achievement award in `year`. False if they already have it (ignoring case)."""
    return _induct(_LIFETIME_ACHIEVERS, name, year)


def find_lifetime_achiever(name: str) -> Inductee | None:
    """The lifetime achievement award winner with this name (ignoring case), or None."""
    return _find(_LIFETIME_ACHIEVERS, name)


def get_lifetime_achievers() -> list[Inductee]:
    """Every lifetime achievement award winner, oldest first, then by name."""
    return _all(_LIFETIME_ACHIEVERS)
