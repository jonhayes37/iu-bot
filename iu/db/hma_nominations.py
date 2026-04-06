"""Database logic for the HMA nomination command"""

import os
import sqlite3
from utils.end_of_year import get_current_award_year

DB_PATH_HMA_NOMINATIONS = os.getenv('DB_PATH_HMA_NOMINATIONS')

def get_family_choices(family_id: str) -> list[tuple[str, str]]:
    """Fetches active categories for a specific family to populate Discord dropdowns."""
    with sqlite3.connect(DB_PATH_HMA_NOMINATIONS) as conn:
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

    with sqlite3.connect(DB_PATH_HMA_NOMINATIONS) as conn:
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
    with sqlite3.connect(DB_PATH_HMA_NOMINATIONS) as conn:
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
