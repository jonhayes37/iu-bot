"""Shared SQLite connection helper for the iu/db/ modules.

db_connection() centralizes the connect / "is the path even set" guard / row_factory steps so
each db function only needs its own try/except and the query logic that's unique to it. The
database file path is looked up from the environment each time it is called (see config.py).

Every connection uses the same settings:
- foreign_keys=ON, so the FOREIGN KEY / ON DELETE CASCADE rules in the schemas are enforced
  (SQLite ignores them unless this is set on each connection).
- a 10 second wait when another connection holds the write lock, instead of SQLite's default 5.
- the connection is closed when the block ends (sqlite3's own `with` only commits or rolls back).

The WAL journal mode was tried and not adopted: each call opens and closes its own connection, and
closing the last connection forces a checkpoint, so WAL saved no time here and added -wal/-shm files.
"""

import contextlib
import sqlite3
from typing import Iterator

from config import Database


BUSY_TIMEOUT_SECONDS = 10


class DatabaseNotConfiguredError(Exception):
    """Raised when the DB_PATH_* environment variable for a database is unset."""


@contextlib.contextmanager
def db_connection(db: Database, row_factory: bool = False) -> Iterator[sqlite3.Connection]:
    """
    Opens a sqlite3 connection to the given database, as a drop-in replacement for
    `with sqlite3.connect(path) as conn:`.

    Commits on a clean exit and rolls back on an exception, exactly like the plain
    `with sqlite3.connect(...)` pattern this replaces.

    Raises DatabaseNotConfiguredError if the database's path isn't set, so callers can fold that
    into the same try/except Exception block they already use for every other database error.
    """
    db_path = db.path
    if not db_path:
        raise DatabaseNotConfiguredError(f"{db.env_var} is not set, so the {db.value} database can't be opened.")

    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_SECONDS)
    try:
        with conn:  # commits on a clean exit, rolls back on an exception
            conn.execute("PRAGMA foreign_keys = ON")
            if row_factory:
                conn.row_factory = sqlite3.Row
            yield conn
    finally:
        conn.close()


def ensure_column(db: Database, table: str, column: str, column_type: str) -> None:
    """
    Adds `column` to `table` if it doesn't already exist.

    SQLite's ALTER TABLE has no "ADD COLUMN IF NOT EXISTS" form (unlike CREATE TABLE/INDEX),
    so schema.sql alone can't retrofit a column onto a database that already exists -- this
    checks PRAGMA table_info first. Safe to call on every startup: a no-op once the column
    is there. table/column/column_type must be trusted, hardcoded callers only, never
    user input -- SQLite can't parameterize identifiers in DDL.
    """
    db_path = db.path
    if not db_path:
        raise DatabaseNotConfiguredError(f"{db.env_var} is not set, so the {db.value} database can't be opened.")

    with sqlite3.connect(db_path) as conn:
        existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
            conn.commit()
