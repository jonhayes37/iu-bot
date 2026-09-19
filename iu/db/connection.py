"""Shared SQLite connection helper for the iu/db/ modules.

db_connection() centralizes the connect / "is the path even set" guard / row_factory steps so
each db function only needs its own try/except and the query logic that's unique to it. The
database file path is looked up from the environment each time it is called (see config.py).
"""

import contextlib
import sqlite3
from typing import Iterator

from config import Database


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

    with sqlite3.connect(db_path) as conn:
        if row_factory:
            conn.row_factory = sqlite3.Row
        yield conn


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
