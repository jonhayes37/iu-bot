"""Tests for db/initialize.py"""

import logging
import sqlite3

import pytest

from config import Database
from db.initialize import COLUMN_MIGRATIONS, _allow_several_releases_per_message, initialize_databases


def _tables(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()


def _columns(path, table) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


class TestInitializeDatabases:
    """initialize_databases builds every configured database from its schema at startup."""

    def test_creates_each_configured_database(self, all_databases):
        for db, path in all_databases.items():
            assert path.exists(), db
            assert _tables(path), db

    def test_every_database_has_a_schema_file(self):
        for db in Database:
            assert db.schema_path.is_file(), db

    def test_skips_databases_that_are_not_configured(self, databases, caplog):
        with caplog.at_level(logging.INFO, logger="iu-bot"):
            databases(Database.MERCH)

        assert Database.LISTS.path is None
        assert "skipping the lists database: DB_PATH_LISTS is not set" in caplog.text

    def test_creates_missing_parent_folders(self, tmp_path, monkeypatch):
        nested = tmp_path / "a" / "b" / "merch.db"
        monkeypatch.setenv("DB_PATH_MERCH", str(nested))

        initialize_databases()

        assert nested.exists()

    def test_running_twice_keeps_the_data(self, databases, execute, query):
        databases(Database.MERCH)
        execute(Database.MERCH, "INSERT INTO users (user_id, balance) VALUES (1, 99)")

        initialize_databases()

        assert query(Database.MERCH, "SELECT balance FROM users")[0]["balance"] == 99

    def test_one_bad_database_does_not_stop_the_others(self, tmp_path, monkeypatch, caplog):
        broken = tmp_path / "broken.db"
        broken.write_text("this is not a sqlite file, and it is long enough to be checked" * 5)
        monkeypatch.setenv("DB_PATH_BOT", str(broken))
        good = tmp_path / "merch.db"
        monkeypatch.setenv("DB_PATH_MERCH", str(good))

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            initialize_databases()

        assert "Failed to initialize DB" in caplog.text
        assert "users" in _tables(good)

    def test_a_missing_schema_file_is_reported_and_does_not_crash(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr("config.SCHEMA_DIR", tmp_path / "no_schemas_here")
        monkeypatch.setenv("DB_PATH_MERCH", str(tmp_path / "merch.db"))

        with caplog.at_level(logging.CRITICAL, logger="iu-bot"):
            initialize_databases()

        assert "Could not find schema file" in caplog.text

    def test_a_failed_column_migration_is_reported_and_startup_carries_on(self, databases, monkeypatch, caplog):
        databases(Database.TOURNAMENTS)

        def broken(*_):
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr("db.initialize.ensure_column", broken)

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            initialize_databases()

        assert "Failed to add tournaments.description" in caplog.text

    def test_a_failed_releases_rebuild_is_reported_and_startup_carries_on(self, databases, monkeypatch, caplog):
        databases(Database.RELEASES)

        def broken(_):
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr("db.initialize._allow_several_releases_per_message", broken)

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            initialize_databases()

        assert "Failed to update the new_releases table" in caplog.text

    def test_reports_rows_that_break_a_foreign_key(self, tmp_path, monkeypatch, caplog):
        path = tmp_path / "lists.db"
        monkeypatch.setenv("DB_PATH_LISTS", str(path))
        initialize_databases()
        conn = sqlite3.connect(path)  # foreign keys are off on a plain connection, so this is allowed
        conn.execute("INSERT INTO list_submissions (event_id, user_id, username, raw_text, cleaned_text) "
                     "VALUES ('ghost', 1, 'a', 'x', 'x')")
        conn.commit()
        conn.close()

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            initialize_databases()

        assert "reference rows that don't exist" in caplog.text


class TestColumnMigrations:
    """COLUMN_MIGRATIONS brings databases created before a column existed up to date."""

    def test_new_databases_already_have_every_migrated_column(self, all_databases):
        for db, table, column, _ in COLUMN_MIGRATIONS:
            assert column in _columns(all_databases[db], table)

    @pytest.mark.parametrize("db, table, column", [(db, table, column) for db, table, column, _ in COLUMN_MIGRATIONS])
    def test_an_old_database_gains_the_column(self, tmp_path, monkeypatch, db, table, column):
        path = tmp_path / f"{db.value}.db"
        monkeypatch.setenv(db.env_var, str(path))
        initialize_databases()
        # Rebuild the table without the column, like a database made before it was added
        conn = sqlite3.connect(path)
        conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.commit()
        conn.close()
        assert column not in _columns(path, table)

        initialize_databases()

        assert column in _columns(path, table)


class TestSeveralReleasesPerMessage:
    """Old releases databases allowed one link per Discord message; startup rebuilds them."""

    OLD_TABLE = """
        CREATE TABLE new_releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            original_url TEXT NOT NULL,
            message_id TEXT UNIQUE NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed BOOLEAN DEFAULT 0
        )
    """

    def _old_database(self, tmp_path, monkeypatch):
        path = tmp_path / "releases.db"
        monkeypatch.setenv("DB_PATH_RELEASES", str(path))
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE youtube_playlists (id INTEGER PRIMARY KEY, year INTEGER, playlist_id TEXT UNIQUE)")
        conn.execute(self.OLD_TABLE)
        conn.execute("INSERT INTO new_releases (video_id, original_url, message_id, processed) "
                     "VALUES ('v1', 'https://youtu.be/v1', 'm1', 1), ('v2', 'https://youtu.be/v2', 'm2', 0)")
        conn.commit()
        conn.close()
        return path

    def test_rebuilds_the_table_and_keeps_every_row(self, tmp_path, monkeypatch):
        path = self._old_database(tmp_path, monkeypatch)

        initialize_databases()

        conn = sqlite3.connect(path)
        rows = conn.execute("SELECT id, video_id, message_id, processed FROM new_releases ORDER BY id").fetchall()
        conn.close()
        assert rows == [(1, "v1", "m1", 1), (2, "v2", "m2", 0)]

    def test_one_message_can_now_hold_several_links(self, tmp_path, monkeypatch):
        path = self._old_database(tmp_path, monkeypatch)

        initialize_databases()

        conn = sqlite3.connect(path)
        conn.execute("INSERT INTO new_releases (video_id, original_url, message_id) VALUES ('v3', 'u', 'm1')")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM new_releases WHERE message_id = 'm1'").fetchone()[0] == 2
        conn.close()

    def test_the_same_link_in_the_same_message_is_still_a_duplicate(self, tmp_path, monkeypatch):
        path = self._old_database(tmp_path, monkeypatch)
        initialize_databases()

        conn = sqlite3.connect(path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO new_releases (video_id, original_url, message_id) VALUES ('v1', 'u', 'm1')")
        conn.close()

    def test_saves_a_copy_of_the_old_database_first(self, tmp_path, monkeypatch):
        self._old_database(tmp_path, monkeypatch)

        initialize_databases()

        copy = tmp_path / "releases.db.before-release-migration"
        assert copy.exists()
        conn = sqlite3.connect(copy)
        assert conn.execute("SELECT COUNT(*) FROM new_releases").fetchone()[0] == 2
        conn.close()

    def test_indexes_survive_the_rebuild(self, tmp_path, monkeypatch):
        path = self._old_database(tmp_path, monkeypatch)

        initialize_databases()

        conn = sqlite3.connect(path)
        names = {row[1] for row in conn.execute("PRAGMA index_list(new_releases)")}
        conn.close()
        assert {"idx_unprocessed_releases", "idx_video_id"} <= names

    def test_a_current_database_is_left_alone(self, databases):
        paths = databases(Database.RELEASES)

        initialize_databases()

        assert not (paths[Database.RELEASES].parent / "releases.db.before-release-migration").exists()

    def test_a_failed_rebuild_changes_nothing(self, tmp_path, monkeypatch):
        path = self._old_database(tmp_path, monkeypatch)
        # A leftover table with the temporary name makes the rename fail part way through
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE new_releases_old (x)")
        conn.commit()
        conn.close()

        with pytest.raises(sqlite3.OperationalError):
            _allow_several_releases_per_message(str(path))

        conn = sqlite3.connect(path)
        assert conn.execute("SELECT COUNT(*) FROM new_releases").fetchone()[0] == 2
        conn.close()
