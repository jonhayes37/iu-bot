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
Keep it that way: a transaction that touches several attached databases (see `attach` below) is only
atomic in the default rollback-journal mode.

ERROR CONTRACT for everything in db/: a function returns normally when it ran, and its result
describes the outcome (None or [] for "nothing found", a bool for "did a row change", an enum when
there are several outcomes). When the database can't be read or written it raises a sqlite3.Error
(DatabaseNotConfiguredError is one too) instead of logging and returning a fallback, so a failure can
never be mistaken for "no data". Expected constraint violations, such as "already registered", are
caught inside the function and returned as an outcome. Errors are reported once, at the command layer
(see ui/base.py), not in every function.
"""

import contextlib
import sqlite3
from typing import Iterator

from config import Database


BUSY_TIMEOUT_SECONDS = 10


class DatabaseNotConfiguredError(sqlite3.Error):
    """Raised when the DB_PATH_* environment variable for a database is unset."""


@contextlib.contextmanager
def db_connection(db: Database, row_factory: bool = False,
                  attach: tuple[Database, ...] = ()) -> Iterator[sqlite3.Connection]:
    """
    Opens a sqlite3 connection to the given database, as a drop-in replacement for
    `with sqlite3.connect(path) as conn:`.

    Commits on a clean exit and rolls back on an exception, exactly like the plain
    `with sqlite3.connect(...)` pattern this replaces.

    Databases listed in `attach` are opened in the same connection under their short name
    (`db.value`), so one transaction can change several of them and either all of it happens or none
    of it does. Query them with the name in front of the table, e.g. `merch.users`.

    Raises DatabaseNotConfiguredError if a database's path isn't set.
    """
    db_path = db.path
    if not db_path:
        raise DatabaseNotConfiguredError(f"{db.env_var} is not set, so the {db.value} database can't be opened.")

    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_SECONDS)
    try:
        with conn:  # commits on a clean exit, rolls back on an exception
            conn.execute("PRAGMA foreign_keys = ON")
            for other in attach:
                if not other.path:
                    raise DatabaseNotConfiguredError(f"{other.env_var} is not set, so the {other.value} database "
                                                     "can't be opened.")
                # The schema name can't be a bound parameter; it comes from the Database enum, not user input
                conn.execute(f"ATTACH DATABASE ? AS {other.value}", (other.path,))
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
