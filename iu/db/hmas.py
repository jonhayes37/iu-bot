"""Database logic for the HMA nomination command.

Every function about one year's awards takes that awards year (the year of the hub or command that asked).
"""
import enum

from config import Database
from db.connection import db_connection

# A Discord select menu holds at most 25 options, and each family is one menu on the nomination form
MAX_CATEGORIES_PER_FAMILY = 25


class AddCategoryResult(enum.Enum):
    """What add_category did."""
    ADDED = "added"
    RESTORED = "restored"               # a removed category with that ID is back, with the new name and family
    ALREADY_ACTIVE = "already_active"
    NAME_TAKEN = "name_taken"           # another active category already has that name
    FAMILY_FULL = "family_full"


class RemoveCategoryResult(enum.Enum):
    """What remove_category did."""
    REMOVED = "removed"
    ALREADY_REMOVED = "already_removed"
    NO_SUCH_CATEGORY = "no_such_category"



def get_family_choices(family_id: str) -> list[tuple[str, str]]:
    """Fetches active categories for a specific family to populate Discord dropdowns."""
    with db_connection(Database.HMAS) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category_id, name
            FROM hma_categories
            WHERE is_active = 1 AND family_id = ?
            ORDER BY name
        """, (family_id,))
        return cursor.fetchall()

def add_nominations(award_year: int, user_id: int, category_ids: list[str], text: str):
    """
    Saves one nomination for each category, all in one transaction (so a failure saves none of
    them).
    """
    with db_connection(Database.HMAS) as conn:
        conn.executemany("""
            INSERT INTO hma_nominations (award_year, category_id, user_id, nomination_text)
            VALUES (?, ?, ?, ?)
        """, [(award_year, category_id, user_id, text) for category_id in category_ids])

def get_yearly_export_data(award_year: int) -> dict[str, dict[str, list[tuple[int, str]]]]:
    """Returns a nested dictionary grouping nominations by Family, then Category."""
    with db_connection(Database.HMAS) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT f.display_name, c.name, n.user_id, n.nomination_text
            FROM hma_nominations n
            JOIN hma_categories c ON n.category_id = c.category_id
            JOIN hma_families f ON c.family_id = f.family_id
            WHERE n.award_year = ?
            ORDER BY f.display_name, c.name, n.submitted_at
        """, (award_year,))

        results = {}
        for family_name, cat_name, u_id, text in cursor.fetchall():
            # Initialize the Family level if it doesn't exist
            if family_name not in results:
                results[family_name] = {}
            # Initialize the Category level if it doesn't exist
            if cat_name not in results[family_name]:
                results[family_name][cat_name] = []

            # Append the nomination
            results[family_name][cat_name].append((u_id, text))

        return results


def set_final_nominees(award_year: int, category_id: str, nominees: list[str]) -> bool:
    """
    Wipes any existing final nominees for the given category/year
    and inserts the new vetted list. Returns False (changing nothing) if there is no such active category.
    """
    with db_connection(Database.HMAS) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM hma_categories WHERE category_id = ? AND is_active = 1", (category_id,))
        if cursor.fetchone() is None:
            return False

        # Clear out the old list
        cursor.execute("""
            DELETE FROM hma_final_nominees
            WHERE category_id = ? AND award_year = ?
        """, (category_id, award_year))

        # Insert the new pipe-separated list
        # We use executemany to do this in a single fast transaction
        cursor.executemany("""
            INSERT INTO hma_final_nominees (category_id, award_year, nominee_name)
            VALUES (?, ?, ?)
        """, [(category_id, award_year, name) for name in nominees])

    return True

def get_active_hma_categories() -> list[dict]:
    """
    The categories in this year's awards (removed ones are left out), Daesangs first, then Bonsangs,
    then Fun awards, each family sorted by name. Each row has category_id, name and family (its display name).
    """
    with db_connection(Database.HMAS, row_factory=True) as conn:
        cursor = conn.cursor()
        # The families were seeded in order (Daesang, Bonsang, Fun), so their rowid gives that order
        cursor.execute("""
            SELECT c.category_id, c.name, f.display_name AS family
            FROM hma_categories c
            JOIN hma_families f ON c.family_id = f.family_id
            WHERE c.is_active = 1
            ORDER BY f.rowid, c.name
        """)
        return [dict(row) for row in cursor.fetchall()]

def add_category(category_id: str, family_id: str, name: str) -> AddCategoryResult:
    """
    Adds an award category, or brings back a removed one with the same ID (taking the new name and
    family). Refuses a duplicate ID or name among the active categories, and a family that is full.
    """
    with db_connection(Database.HMAS) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT is_active FROM hma_categories WHERE category_id = ?", (category_id,)).fetchone()
        if existing and existing[0]:
            return AddCategoryResult.ALREADY_ACTIVE

        same_name = conn.execute(
            "SELECT 1 FROM hma_categories WHERE is_active = 1 AND name = ? COLLATE NOCASE", (name,)).fetchone()
        if same_name:
            return AddCategoryResult.NAME_TAKEN

        in_family = conn.execute(
            "SELECT COUNT(*) FROM hma_categories WHERE is_active = 1 AND family_id = ?", (family_id,)).fetchone()[0]
        if in_family >= MAX_CATEGORIES_PER_FAMILY:
            return AddCategoryResult.FAMILY_FULL

        if existing:
            conn.execute("UPDATE hma_categories SET family_id = ?, name = ?, is_active = 1 WHERE category_id = ?",
                         (family_id, name, category_id))
            return AddCategoryResult.RESTORED

        conn.execute("INSERT INTO hma_categories (category_id, family_id, name, is_active) VALUES (?, ?, ?, 1)",
                     (category_id, family_id, name))
        return AddCategoryResult.ADDED

def remove_category(category_id: str) -> RemoveCategoryResult:
    """
    Takes a category out of the awards. Its row, nominations, finalists and votes are kept (other
    tables refer to it), so adding it again with the same ID brings it all back.
    """
    with db_connection(Database.HMAS) as conn:
        row = conn.execute("SELECT is_active FROM hma_categories WHERE category_id = ?", (category_id,)).fetchone()
        if row is None:
            return RemoveCategoryResult.NO_SUCH_CATEGORY
        if not row[0]:
            return RemoveCategoryResult.ALREADY_REMOVED
        conn.execute("UPDATE hma_categories SET is_active = 0 WHERE category_id = ?", (category_id,))
        return RemoveCategoryResult.REMOVED

def get_hma_ballots(award_year: int) -> dict[str, list[tuple[str, str, str]]]:
    """Every (1st, 2nd, 3rd choice) ballot cast for the year, by category ID."""
    with db_connection(Database.HMAS) as conn:
        rows = conn.execute("""
            SELECT category_id, first_choice, second_choice, third_choice
            FROM hma_votes
            WHERE award_year = ?
        """, (award_year,)).fetchall()

    ballots: dict[str, list[tuple[str, str, str]]] = {}
    for category_id, first, second, third in rows:
        ballots.setdefault(category_id, []).append((first, second, third))
    return ballots

def get_user_hma_votes(award_year: int, user_id: int) -> dict:
    """Fetches a user's existing votes, keyed by category_id for instant lookups."""
    with db_connection(Database.HMAS, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category_id, first_choice, second_choice, third_choice
            FROM hma_votes
            WHERE user_id = ? AND award_year = ?
        """, (user_id, award_year))
        # Return a dictionary formatted like: {'soty': {'first_choice': 'IVE', ...}}
        return {row['category_id']: dict(row) for row in cursor.fetchall()}

def get_hma_final_nominees(award_year: int, category_id: str) -> list[str]:
    """Fetches the vetted list of final nominees for a specific category."""
    with db_connection(Database.HMAS) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nominee_name FROM hma_final_nominees
            WHERE category_id = ? AND award_year = ?
            ORDER BY nominee_name
        """, (category_id, award_year))
        return [row[0] for row in cursor.fetchall()]

def save_hma_vote(award_year: int, user_id: int, category_id: str, first: str, second: str, third: str):
    """Saves or updates a user's ranked HMA ballot for a specific category."""
    with db_connection(Database.HMAS) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO hma_votes
            (user_id, award_year, category_id, first_choice, second_choice, third_choice)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, award_year, category_id, first, second, third))

def save_category_suggestion(award_year: int, user_id: int, username: str, new_cats: str, dropped_cats: str):
    """Saves or updates a user's HMA category suggestions."""
    with db_connection(Database.HMAS) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO hma_category_suggestions
            (user_id, award_year, username, new_categories, dropped_categories)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, award_year, username, new_cats, dropped_cats))

def get_user_category_suggestion(award_year: int, user_id: int) -> dict | None:
    """Fetches a user's existing suggestions to pre-fill the modal."""
    with db_connection(Database.HMAS, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT new_categories, dropped_categories
            FROM hma_category_suggestions
            WHERE user_id = ? AND award_year = ?
        """, (user_id, award_year))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_category_suggestions(award_year: int) -> list[dict]:
    """Fetches all suggestions for the award year to be exported."""
    with db_connection(Database.HMAS, row_factory=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hma_category_suggestions WHERE award_year = ?", (award_year,))
        return [dict(row) for row in cursor.fetchall()]

def get_current_categories_by_family() -> dict[str, list[str]]:
    """Fetches all current active categories grouped by family name."""
    with db_connection(Database.HMAS) as conn:
        cursor = conn.cursor()
        # Updated to match your exact schema columns!
        cursor.execute("""
            SELECT f.display_name, c.name
            FROM hma_families f
            JOIN hma_categories c ON f.family_id = c.family_id
            WHERE c.is_active = 1
            ORDER BY f.display_name ASC, c.name ASC
        """)

        results = {}
        for family_name, category_name in cursor.fetchall():
            if family_name not in results:
                results[family_name] = []
            results[family_name].append(category_name)

        return results
