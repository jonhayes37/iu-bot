"""Logic for the roles DB"""


import logging
import os
import sqlite3

logger = logging.getLogger('iu-bot')

DB_PATH_ROLES = os.getenv('DB_PATH_ROLES')

def get_role_id(alias: str) -> int | None:
    """Fetches the Discord Role ID associated with a given name or alias."""
    if not DB_PATH_ROLES:
        logger.error("DB_PATH_ROLES environment variable not set! Cannot access roles database.")
        return None

    try:
        with sqlite3.connect(DB_PATH_ROLES) as conn:
            cursor = conn.cursor()
            # UNION merges the results. LOWER(role_name) ensures case-insensitive
            # matching against the user's lowercased input.
            cursor.execute("""
                SELECT role_id FROM role_aliases WHERE alias = ?
                UNION
                SELECT role_id FROM assignable_roles WHERE LOWER(role_name) = ?
            """, (alias, alias))
            result = cursor.fetchone()
            return result[0] if result else None
    except Exception as ex:
        logger.error("Error occurred while fetching role ID for alias '%s': %s", alias, ex)
        return None

def get_all_roles_grouped() -> dict:
    """Fetches all roles and aliases, grouped by category."""
    if not DB_PATH_ROLES:
        return {}

    try:
        with sqlite3.connect(DB_PATH_ROLES) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.name, r.role_name, a.alias
                FROM role_categories c
                JOIN assignable_roles r ON c.category_id = r.category_id
                LEFT JOIN role_aliases a ON r.role_id = a.role_id
                ORDER BY c.display_order, r.role_name, a.alias
            """)

            grouped = {}
            for cat_name, role_name, alias in cursor.fetchall():
                if cat_name not in grouped:
                    grouped[cat_name] = {}
                if role_name not in grouped[cat_name]:
                    grouped[cat_name][role_name] = []

                if alias:
                    grouped[cat_name][role_name].append(alias)

            return grouped
    except Exception as ex:
        logger.error("Failed to fetch grouped roles: %s", ex)
        return {}

def get_display_message_ids() -> list[int]:
    """Retrieves the list of active message IDs from the database."""
    if not DB_PATH_ROLES:
        logger.error("DB_PATH_ROLES environment variable not set! Cannot fetch display message IDs.")
        return []

    try:
        with sqlite3.connect(DB_PATH_ROLES) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message_id FROM display_messages")
            return [row[0] for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Failed to fetch display message IDs: %s", ex)
        return []

def replace_display_message_ids(message_ids: list[int]):
    """Wipes the old tracked IDs and saves the new ones."""
    if not DB_PATH_ROLES:
        logger.error("DB_PATH_ROLES environment variable not set! Cannot update display message IDs.")
        return

    try:
        with sqlite3.connect(DB_PATH_ROLES) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM display_messages")
            cursor.executemany("INSERT INTO display_messages (message_id) VALUES (?)", [(m,) for m in message_ids])
            # The context manager automatically calls conn.commit() upon successful exit
    except Exception as ex:
        logger.error("Failed to replace display message IDs: %s", ex)

def register_new_role(role_id: int, role_name: str, category_name: str, aliases: list[str]) -> bool:
    """Inserts a new role, its category, and its aliases into the database."""
    if not DB_PATH_ROLES:
        return False

    try:
        with sqlite3.connect(DB_PATH_ROLES) as conn:
            cursor = conn.cursor()

            # Upsert the category
            cursor.execute("SELECT category_id FROM role_categories WHERE name = ?", (category_name,))
            cat_result = cursor.fetchone()
            if cat_result:
                category_id = cat_result[0]
            else:
                cursor.execute("INSERT INTO role_categories (name) VALUES (?)", (category_name,))
                category_id = cursor.lastrowid

            # Add the role
            cursor.execute("""
                INSERT OR REPLACE INTO assignable_roles (role_id, category_id, role_name) 
                VALUES (?, ?, ?)
            """, (role_id, category_id, role_name))

            # Add aliases (Always include the exact lowercased role name as a free alias)
            all_aliases = set([a.strip().lower() for a in aliases if a.strip()])
            all_aliases.add(role_name.lower())

            for alias in all_aliases:
                cursor.execute("""
                    INSERT OR IGNORE INTO role_aliases (alias, role_id) 
                    VALUES (?, ?)
                """, (alias, role_id))

            return True

    except Exception as ex:
        logger.error("Failed to register new role '%s': %s", role_name, ex)
        return False
