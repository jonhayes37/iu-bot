"""Database functions for bias embeds"""
import sqlite3
import logging
import os

logger = logging.getLogger('iu-bot')

DB_PATH_BIASES = os.getenv('DB_PATH_BIASES', 'db/biases.db')

def create_ultimate_bias_db(user_id: int, name: str, birth_name: str, birthday: str,
                            colour: int, group_name: str, hometown: str,
                            image_filename: str, position: str, reason: str) -> bool:
    """Inserts a new ultimate bias record for a user."""
    try:
        with sqlite3.connect(DB_PATH_BIASES) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ultimate_biases 
                (user_id, name, birth_name, birthday, colour, group_name, hometown, image_filename, position, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, name, birth_name, birthday, colour, group_name, hometown, image_filename, position, reason))
            return True

    except sqlite3.IntegrityError:
        logger.error("Ultimate bias creation failed: User %s already has an entry.", user_id)
        return False
    except Exception as ex:
        logger.error("Database error creating ultimate bias: %s", ex)
        return False

def update_ultimate_bias_db(user_id: int, **updates) -> bool:
    """Updates an existing ultimate bias record. Returns False if user doesn't exist."""
    if not updates:
        return False

    try:
        with sqlite3.connect(DB_PATH_BIASES) as conn:
            cursor = conn.cursor()

            # Dynamically construct the SET clause based on provided arguments
            set_clauses = []
            values = []
            for key, value in updates.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)

            # Add the user_id to the end of the values list for the WHERE clause
            values.append(user_id)

            query = f"UPDATE ultimate_biases SET {', '.join(set_clauses)} WHERE user_id = ?"
            cursor.execute(query, tuple(values))

            # If rowcount is 0, the UPDATE failed because the user_id wasn't found
            return cursor.rowcount > 0

    except Exception as ex:
        logger.error("Database error updating ultimate bias for %s: %s", user_id, ex)
        return False

def get_ultimate_bias(user_id: int) -> dict:
    """Fetches the ultimate bias record for a user."""
    try:
        with sqlite3.connect(DB_PATH_BIASES) as conn:
            # Using Row factory allows us to access columns by name (like a dictionary)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM ultimate_biases WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    except Exception as ex:
        logger.error("Database error fetching ultimate bias for %s: %s", user_id, ex)
        return None

def create_artist_bias_db(
    user_id: int, name: str, album: str, b_track: str, bias: str,
    colour: int, debut_date: str, image_filename: str, label: str,
    members: str, reason: str, title_track: str
) -> bool:
    """Inserts a new artist bias (bias group) record for a user."""
    try:
        with sqlite3.connect(DB_PATH_BIASES) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO artist_biases 
                (user_id, name, album, b_track, bias, colour, debut_date, image_filename, label, members, reason, title_track)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, name, album, b_track, bias, colour, debut_date, image_filename, label, members, reason,
                  title_track))
            return True

    except sqlite3.IntegrityError:
        logger.error("Artist bias creation failed: User %s already has an entry.", user_id)
        return False
    except Exception as ex:
        logger.error("Database error creating artist bias for %s: %s", user_id, ex)
        return False

def update_artist_bias_db(user_id: int, **updates) -> bool:
    """Updates an existing artist bias record. Returns False if user doesn't exist."""
    if not updates:
        return False

    try:
        with sqlite3.connect(DB_PATH_BIASES) as conn:
            cursor = conn.cursor()

            set_clauses = []
            values = []
            for key, value in updates.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)

            values.append(user_id) 

            query = f"UPDATE artist_biases SET {', '.join(set_clauses)} WHERE user_id = ?"
            cursor.execute(query, tuple(values))

            return cursor.rowcount > 0

    except Exception as ex:
        logger.error("Database error updating artist bias for %s: %s", user_id, ex)
        return False

def get_artist_bias(user_id: int) -> dict:
    """Fetches the artist bias record for a user."""
    try:
        with sqlite3.connect(DB_PATH_BIASES) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM artist_biases WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    except Exception as ex:
        logger.error("Database error fetching artist bias for %s: %s", user_id, ex)
        return None
