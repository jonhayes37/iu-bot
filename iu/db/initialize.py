"""Creates the SQLite databases and brings older ones up to date."""

import logging
import os
import sqlite3

from config import Database
from db.connection import ensure_column

logger = logging.getLogger('iu-bot')

# CREATE TABLE IF NOT EXISTS won't add a column to a table that already exists, so columns added
# after a database was first created are patched in here: (database, table, column, column type).
COLUMN_MIGRATIONS = [
    # tournaments.db predates the `description` column that create_tournament() writes to.
    (Database.TOURNAMENTS, "tournaments", "description", "TEXT"),
    # Tracks how far an interrupted listen game reveal got, so it can resume.
    (Database.LISTEN_GAME, "listen_rounds", "reveal_step", "INTEGER NOT NULL DEFAULT 0"),
]


def initialize_databases():
    """Creates every configured database from its schema file, then applies column migrations."""
    logger.info("Initializing databases...")
    for db in Database:
        db_path = db.path
        if not db_path:
            logger.info("skipping the %s database: %s is not set", db.value, db.env_var)
            continue

        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        try:
            with open(db.schema_path, 'r', encoding='utf-8') as file:
                schema_script = file.read()
            with sqlite3.connect(db_path) as conn:
                conn.executescript(schema_script)
                conn.commit()
        except FileNotFoundError:
            logger.critical("Error: Could not find schema file at %s", db.schema_path)
        except Exception as e:
            logger.error("Failed to initialize DB at %s: %s", db_path, e)

    # Each migration is a no-op once the column exists, so this is safe to run on every startup.
    for db, table, column, column_type in COLUMN_MIGRATIONS:
        if not db.path:
            continue
        try:
            ensure_column(db, table, column, column_type)
        except Exception as e:
            logger.error("Failed to add %s.%s to the %s database: %s", table, column, db.value, e)

    logger.info("All databases initialized successfully.")
