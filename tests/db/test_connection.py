"""Tests for db/connection.py"""

import sqlite3

import pytest

from config import Database
from db.connection import BUSY_TIMEOUT_SECONDS, DatabaseNotConfiguredError, db_connection, ensure_column
from db.errors import InvalidStateError


class TestDbConnection:
    """db_connection opens, configures, commits or rolls back, and always closes."""

    def test_unset_path_raises_a_sqlite_error_naming_the_variable(self):
        with pytest.raises(DatabaseNotConfiguredError, match="DB_PATH_MERCH is not set"):
            with db_connection(Database.MERCH):
                pass

    def test_not_configured_is_a_sqlite_error(self):
        # Callers catch sqlite3.Error for "the database couldn't be used", so this must qualify
        assert issubclass(DatabaseNotConfiguredError, sqlite3.Error)

    def test_commits_on_a_clean_exit(self, databases, query):
        databases(Database.MERCH)

        with db_connection(Database.MERCH) as conn:
            conn.execute("INSERT INTO users (user_id, balance) VALUES (1, 50)")

        assert query(Database.MERCH, "SELECT balance FROM users WHERE user_id = 1")[0]["balance"] == 50

    def test_rolls_back_when_the_block_raises(self, databases, query):
        databases(Database.MERCH)

        with pytest.raises(RuntimeError):
            with db_connection(Database.MERCH) as conn:
                conn.execute("INSERT INTO users (user_id, balance) VALUES (1, 50)")
                raise RuntimeError("boom")

        assert query(Database.MERCH, "SELECT * FROM users") == []

    def test_connection_is_closed_afterwards(self, databases):
        databases(Database.MERCH)

        with db_connection(Database.MERCH) as conn:
            pass

        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_connection_is_closed_even_after_an_error(self, databases):
        databases(Database.MERCH)

        with pytest.raises(RuntimeError):
            with db_connection(Database.MERCH) as conn:
                raise RuntimeError("boom")

        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_foreign_keys_are_enforced(self, databases):
        databases(Database.LISTS)

        with pytest.raises(sqlite3.IntegrityError):
            with db_connection(Database.LISTS) as conn:
                conn.execute("INSERT INTO list_submissions (event_id, user_id, username, raw_text, cleaned_text) "
                             "VALUES ('missing', 1, 'a', 'x', 'x')")

    def test_waits_up_to_ten_seconds_for_a_lock(self, databases):
        databases(Database.MERCH)

        with db_connection(Database.MERCH) as conn:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_SECONDS * 1000

    def test_keeps_the_default_journal_mode(self, databases):
        # WAL would make a transaction across attached databases no longer all-or-nothing
        databases(Database.MERCH)

        with db_connection(Database.MERCH) as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"

    def test_rows_are_plain_tuples_by_default(self, databases):
        databases(Database.MERCH)

        with db_connection(Database.MERCH) as conn:
            conn.execute("INSERT INTO users (user_id, balance) VALUES (1, 50)")
            row = conn.execute("SELECT user_id, balance FROM users").fetchone()

        assert row == (1, 50)
        assert not isinstance(row, sqlite3.Row)

    def test_row_factory_gives_access_by_column_name(self, databases):
        databases(Database.MERCH)

        with db_connection(Database.MERCH, row_factory=True) as conn:
            conn.execute("INSERT INTO users (user_id, balance) VALUES (1, 50)")
            row = conn.execute("SELECT user_id, balance FROM users").fetchone()

        assert row["balance"] == 50


class TestAttach:
    """`attach` puts other databases in the same connection so one transaction spans them."""

    def test_attached_database_is_queried_by_its_short_name(self, databases, execute):
        databases(Database.LISTS, Database.MERCH)
        execute(Database.MERCH, "INSERT INTO users (user_id, balance) VALUES (7, 70)")

        with db_connection(Database.LISTS, attach=(Database.MERCH,)) as conn:
            assert conn.execute("SELECT balance FROM merch.users WHERE user_id = 7").fetchone()[0] == 70

    def test_changes_to_both_databases_commit_together(self, databases, query):
        databases(Database.LISTS, Database.MERCH)

        with db_connection(Database.LISTS, attach=(Database.MERCH,)) as conn:
            conn.execute("INSERT INTO list_events (event_id, event_name) VALUES ('e', 'Event')")
            conn.execute("INSERT INTO merch.users (user_id, balance) VALUES (1, 5)")

        assert len(query(Database.LISTS, "SELECT * FROM list_events")) == 1
        assert len(query(Database.MERCH, "SELECT * FROM users")) == 1

    def test_an_error_undoes_the_changes_in_both_databases(self, databases, query):
        databases(Database.LISTS, Database.MERCH)

        with pytest.raises(RuntimeError):
            with db_connection(Database.LISTS, attach=(Database.MERCH,)) as conn:
                conn.execute("INSERT INTO list_events (event_id, event_name) VALUES ('e', 'Event')")
                conn.execute("INSERT INTO merch.users (user_id, balance) VALUES (1, 5)")
                raise RuntimeError("boom")

        assert query(Database.LISTS, "SELECT * FROM list_events") == []
        assert query(Database.MERCH, "SELECT * FROM users") == []

    def test_unset_attached_database_raises(self, databases):
        databases(Database.LISTS)

        with pytest.raises(DatabaseNotConfiguredError, match="DB_PATH_MERCH"):
            with db_connection(Database.LISTS, attach=(Database.MERCH,)):
                pass


class TestEnsureColumn:
    """ensure_column adds a missing column and does nothing if it is already there."""

    def test_adds_a_missing_column(self, databases, query):
        databases(Database.BOT)

        ensure_column(Database.BOT, "statuses", "note", "TEXT")

        assert "note" in [row["name"] for row in query(Database.BOT, "PRAGMA table_info(statuses)")]

    def test_is_a_no_op_when_the_column_exists(self, databases, query):
        databases(Database.BOT)

        ensure_column(Database.BOT, "statuses", "note", "TEXT")
        ensure_column(Database.BOT, "statuses", "note", "TEXT")

        assert [row["name"] for row in query(Database.BOT, "PRAGMA table_info(statuses)")].count("note") == 1

    def test_existing_rows_keep_their_data_and_get_the_default(self, databases, execute, query):
        databases(Database.BOT)
        execute(Database.BOT, "INSERT INTO statuses (status_text) VALUES ('hi')")

        ensure_column(Database.BOT, "statuses", "level", "INTEGER NOT NULL DEFAULT 3")

        row = query(Database.BOT, "SELECT status_text, level FROM statuses")[0]
        assert (row["status_text"], row["level"]) == ("hi", 3)

    def test_unset_path_raises(self):
        with pytest.raises(DatabaseNotConfiguredError):
            ensure_column(Database.BOT, "statuses", "note", "TEXT")


def test_invalid_state_error_is_not_a_database_error():
    # It means "things moved on", not "the database failed", and is reported differently
    assert not issubclass(InvalidStateError, sqlite3.Error)
    assert issubclass(InvalidStateError, Exception)
