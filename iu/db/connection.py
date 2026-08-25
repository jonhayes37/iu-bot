"""Shared SQLite connection helper for the iu/db/ modules.

Every db/*.py module independently repeated the same shape: open a
`with sqlite3.connect(DB_PATH_X) as conn:` block (some also guarded it with an
"is DB_PATH_X even set" check first, others didn't), optionally set
`conn.row_factory = sqlite3.Row`, then let a try/except around the whole thing handle
failures. db_connection() centralizes the connect/guard/row_factory steps so each db
function only needs its own try/except and the query logic that's actually unique to it.
"""

import contextlib
import sqlite3
from typing import Iterator


class DatabaseNotConfiguredError(Exception):
    """Raised when a DB_PATH_* environment variable required for this operation is unset."""


@contextlib.contextmanager
def db_connection(db_path: str | None, row_factory: bool = False) -> Iterator[sqlite3.Connection]:
    """
    Opens a sqlite3 connection to db_path, as a drop-in replacement for
    `with sqlite3.connect(db_path) as conn:`.

    Commits on a clean exit and rolls back on an exception, exactly like the plain
    `with sqlite3.connect(...)` pattern this replaces.

    Raises DatabaseNotConfiguredError if db_path is falsy, so callers can fold that into
    the same try/except Exception block they already use for every other database error.
    """
    if not db_path:
        raise DatabaseNotConfiguredError(
            "A DB_PATH_* environment variable is not set for this operation."
        )

    with sqlite3.connect(db_path) as conn:
        if row_factory:
            conn.row_factory = sqlite3.Row
        yield conn


def ensure_column(db_path: str, table: str, column: str, column_type: str) -> None:
    """
    Adds `column` to `table` if it doesn't already exist.

    SQLite's ALTER TABLE has no "ADD COLUMN IF NOT EXISTS" form (unlike CREATE TABLE/INDEX),
    so schema.sql alone can't retrofit a column onto a database that already exists -- this
    checks PRAGMA table_info first. Safe to call on every startup: a no-op once the column
    is there. table/column/column_type must be trusted, hardcoded callers only, never
    user input -- SQLite can't parameterize identifiers in DDL.
    """
    with sqlite3.connect(db_path) as conn:
        existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
            conn.commit()
