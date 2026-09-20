"""Logic for the roles DB"""


from dataclasses import dataclass
from config import Database
from db.connection import db_connection


@dataclass(frozen=True)
class AliasClash:
    """A name a new role wants that another role already answers to."""
    alias: str
    role_id: int
    role_name: str


def get_role_id(alias: str) -> int | None:
    """Fetches the Discord Role ID associated with a given name or alias."""
    with db_connection(Database.ROLES) as conn:
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

def get_all_roles_grouped() -> dict:
    """Fetches all roles and aliases, grouped by category."""
    with db_connection(Database.ROLES) as conn:
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

def get_display_message_ids() -> list[int]:
    """Retrieves the list of active message IDs from the database."""
    with db_connection(Database.ROLES) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message_id FROM display_messages")
        return [row[0] for row in cursor.fetchall()]

def replace_display_message_ids(message_ids: list[int]):
    """Wipes the old tracked IDs and saves the new ones."""
    with db_connection(Database.ROLES) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM display_messages")
        cursor.executemany("INSERT INTO display_messages (message_id) VALUES (?)", [(m,) for m in message_ids])

def register_new_role(role_id: int, role_name: str, category_name: str, aliases: list[str]) -> list[AliasClash]:
    """
    Inserts a new role, its category, and its aliases into the database.

    Every alias (including the role's own lowercased name, which is always one) must be free: not
    already an alias of, or the name of, a different role, or `get_role_id` couldn't tell which role
    someone meant. If any are taken, nothing is saved and the clashes are returned. An empty list means
    the role was saved. Registering a role again (to rename it or add aliases) is fine.
    """
    all_aliases = {a.strip().lower() for a in aliases if a.strip()}
    all_aliases.add(role_name.lower())

    with db_connection(Database.ROLES) as conn:
        # Take the write lock before checking, so two registrations at once can't claim the same alias
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()

        clashes = []
        for alias in sorted(all_aliases):
            cursor.execute("""
                SELECT r.role_id, r.role_name FROM role_aliases a
                JOIN assignable_roles r ON r.role_id = a.role_id
                WHERE a.alias = ? AND a.role_id != ?
                UNION
                SELECT role_id, role_name FROM assignable_roles WHERE LOWER(role_name) = ? AND role_id != ?
            """, (alias, role_id, alias, role_id))
            owner = cursor.fetchone()
            if owner:
                clashes.append(AliasClash(alias, owner[0], owner[1]))
        if clashes:
            return clashes

        # Upsert the category
        cursor.execute("SELECT category_id FROM role_categories WHERE name = ?", (category_name,))
        cat_result = cursor.fetchone()
        if cat_result:
            category_id = cat_result[0]
        else:
            cursor.execute("INSERT INTO role_categories (name) VALUES (?)", (category_name,))
            category_id = cursor.lastrowid

        # Add the role
        # An upsert, not INSERT OR REPLACE: replacing the row would delete it first, and with
        # foreign keys on that would also delete all of the role's existing aliases.
        cursor.execute("""
            INSERT INTO assignable_roles (role_id, category_id, role_name)
            VALUES (?, ?, ?)
            ON CONFLICT(role_id) DO UPDATE SET category_id = excluded.category_id, role_name = excluded.role_name
        """, (role_id, category_id, role_name))

        for alias in all_aliases:
            cursor.execute("INSERT OR IGNORE INTO role_aliases (alias, role_id) VALUES (?, ?)", (alias, role_id))

        return []
