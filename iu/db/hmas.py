"""Database logic for the HMA nomination command"""
import logging
import os
import sqlite3
from utils.end_of_year import get_current_award_year

DB_PATH_HMAS = os.getenv('DB_PATH_HMAS')

logger = logging.getLogger('iu-bot')


def get_family_choices(family_id: str) -> list[tuple[str, str]]:
    """Fetches active categories for a specific family to populate Discord dropdowns."""
    with sqlite3.connect(DB_PATH_HMAS) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category_id, name 
            FROM hma_categories 
            WHERE is_active = 1 AND family_id = ?
            ORDER BY name
        """, (family_id,))
        return cursor.fetchall()

def add_nomination(user_id: int, category_id: str, text: str) -> int:
    """Saves the nomination securely and returns the calculated award year."""
    award_year = get_current_award_year()

    with sqlite3.connect(DB_PATH_HMAS) as conn:
        # Crucial: Enable foreign keys so SQLite enforces the category_id check
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO hma_nominations (award_year, category_id, user_id, nomination_text)
            VALUES (?, ?, ?, ?)
        """, (award_year, category_id, user_id, text))

        conn.commit()
        return award_year

def get_yearly_export_data(award_year: int) -> dict[str, dict[str, list[tuple[int, str]]]]:
    """Returns a nested dictionary grouping nominations by Family, then Category."""
    with sqlite3.connect(DB_PATH_HMAS) as conn:
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


def set_final_nominees(category_id: str, nominees: list[str]) -> int:
    """
    Wipes any existing final nominees for the given category/year 
    and inserts the new vetted list.
    """
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HMAS) as conn:
            cursor = conn.cursor()

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

            conn.commit()

        return award_year
    except Exception as ex:
        logger.error("Failed to set final nominees for %s: %s", category_id, ex)
        raise

# Add to db/hmas.py

def get_all_hma_categories() -> list[dict]:
    """Fetches all award categories."""
    try:
        with sqlite3.connect(DB_PATH_HMAS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT category_id, name FROM hma_categories ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Failed to fetch HMA categories: %s", ex)
        return []

def get_user_hma_votes(user_id: int) -> dict:
    """Fetches a user's existing votes, keyed by category_id for instant lookups."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HMAS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT category_id, first_choice, second_choice, third_choice 
                FROM hma_votes 
                WHERE user_id = ? AND award_year = ?
            """, (user_id, award_year))
            # Return a dictionary formatted like: {'soty': {'first_choice': 'IVE', ...}}
            return {row['category_id']: dict(row) for row in cursor.fetchall()}
    except Exception as ex:
        logger.error("Failed to fetch HMA votes for %s: %s", user_id, ex)
        return {}

def get_hma_final_nominees(category_id: str) -> list[str]:
    """Fetches the vetted list of final nominees for a specific category."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HMAS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT nominee_name FROM hma_final_nominees 
                WHERE category_id = ? AND award_year = ? 
                ORDER BY nominee_name
            """, (category_id, award_year))
            return [row[0] for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Failed to fetch official HMA nominees: %s", ex)
        return []

def save_hma_vote(user_id: int, category_id: str, first: str, second: str, third: str):
    """Saves or updates a user's ranked HMA ballot for a specific category."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HMAS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO hma_votes 
                (user_id, award_year, category_id, first_choice, second_choice, third_choice)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, award_year, category_id, first, second, third))
            conn.commit()
    except Exception as ex:
        logger.error("Failed to save HMA vote for %s: %s", user_id, ex)
        raise

def save_category_suggestion(user_id: int, username: str, new_cats: str, dropped_cats: str) -> int:
    """Saves or updates a user's HMA category suggestions."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HMAS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO hma_category_suggestions 
                (user_id, award_year, username, new_categories, dropped_categories)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, award_year, username, new_cats, dropped_cats))
            conn.commit()
        return award_year
    except Exception as ex:
        logger.error("Failed to save HMA category suggestion for %s: %s", user_id, ex)
        raise

def get_user_category_suggestion(user_id: int) -> dict | None:
    """Fetches a user's existing suggestions to pre-fill the modal."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HMAS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT new_categories, dropped_categories 
                FROM hma_category_suggestions 
                WHERE user_id = ? AND award_year = ?
            """, (user_id, award_year))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as ex:
        logger.error("Failed to fetch HMA suggestion for %s: %s", user_id, ex)
        return None

def get_all_category_suggestions() -> list[dict]:
    """Fetches all suggestions for the current award year to be exported."""
    award_year = get_current_award_year()
    try:
        with sqlite3.connect(DB_PATH_HMAS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hma_category_suggestions WHERE award_year = ?", (award_year,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Failed to fetch all HMA suggestions for year %s: %s", award_year, ex)
        return []

def get_current_categories_by_family() -> dict[str, list[str]]:
    """Fetches all current active categories grouped by family name."""
    try:
        with sqlite3.connect(DB_PATH_HMAS) as conn:
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
    except Exception as ex:
        logger.error("Failed to fetch categories by family: %s", ex)
        return {}
