"""Creates the SQLite databases and brings older ones up to date."""

import contextlib
import logging
import os
import sqlite3

from config import Database
from db.connection import ensure_column

logger = logging.getLogger('iu-bot')

# The current definition of new_releases (keep in step with db/schema/releases.sql). Used to rebuild
# databases created when message_id was UNIQUE on its own, which allowed only one link per message.
_NEW_RELEASES_TABLE_SQL = """
    CREATE TABLE new_releases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT UNIQUE NOT NULL,
        original_url TEXT NOT NULL,
        message_id TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        processed BOOLEAN DEFAULT 0,
        UNIQUE (message_id, video_id)
    )
"""

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
            with contextlib.closing(sqlite3.connect(db_path)) as conn:
                conn.executescript(schema_script)
                conn.commit()
                _check_foreign_keys(conn, db)
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

    if Database.RELEASES.path:
        try:
            _allow_several_releases_per_message(Database.RELEASES.path)
        except Exception as e:
            logger.error("Failed to update the new_releases table: %s", e)

    logger.info("All databases initialized successfully.")


def _check_foreign_keys(conn: sqlite3.Connection, db: Database):
    """Reports rows that break the schema's foreign keys, which are now enforced on every write."""
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        logger.warning("The %s database has %d rows that reference rows that don't exist (first: %s).",
                       db.value, len(violations), tuple(violations[0]))


def _has_unique_index(conn: sqlite3.Connection, table: str, columns: list[str]) -> bool:
    """True if the table has a UNIQUE constraint on exactly these columns."""
    for _, index_name, is_unique, *_ in conn.execute(f"PRAGMA index_list({table})").fetchall():
        index_columns = [row[2] for row in conn.execute(f"PRAGMA index_info({index_name})").fetchall()]
        if is_unique and index_columns == columns:
            return True
    return False


def _allow_several_releases_per_message(db_path: str):
    """
    Rebuilds new_releases so message_id is no longer UNIQUE by itself. SQLite can't drop a
    constraint in place, so the rows are copied into a new table inside one transaction: either
    everything is swapped or nothing changes. A no-op once the table has been rebuilt.
    """
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        if not _has_unique_index(conn, "new_releases", ["message_id"]):
            return

        backup_path = f"{db_path}.before-release-migration"
        if not os.path.exists(backup_path):
            with contextlib.closing(sqlite3.connect(backup_path)) as backup:
                conn.backup(backup)
            logger.info("Saved a copy of the releases database to %s", backup_path)

        conn.execute("BEGIN")
        try:
            conn.execute("ALTER TABLE new_releases RENAME TO new_releases_old")
            conn.execute(_NEW_RELEASES_TABLE_SQL)
            conn.execute("""
                INSERT INTO new_releases (id, video_id, original_url, message_id, timestamp, processed)
                SELECT id, video_id, original_url, message_id, timestamp, processed FROM new_releases_old
            """)
            conn.execute("DROP TABLE new_releases_old")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_unprocessed_releases ON new_releases(processed)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_video_id ON new_releases(video_id)")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        logger.info("Rebuilt new_releases so one message can hold several links.")
