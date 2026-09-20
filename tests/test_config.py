"""Tests for config.py: settings read from the environment, and the database list."""

import pytest

from config import (
    DEFAULT_ADMIN_USER_ID, MEDIA_DIR, SCHEMA_DIR, Channel, Database, Role, admin_user_id, discord_token, guild_id,
    log_level, youtube_token_path
)


class TestEnvironmentSettings:
    """Each setting is read when asked for, so a test (or a restart) sees the current value."""

    def test_the_token(self, monkeypatch):
        assert discord_token() is None
        monkeypatch.setenv("DISCORD_TOKEN", "abc")

        assert discord_token() == "abc"

    def test_the_server_id_is_a_number_or_none(self, monkeypatch):
        assert guild_id() is None
        monkeypatch.setenv("DISCORD_GUILD", "795846406187384842")

        assert guild_id() == 795846406187384842

    def test_a_blank_server_id_means_none(self, monkeypatch):
        monkeypatch.setenv("DISCORD_GUILD", "")

        assert guild_id() is None

    def test_a_server_id_that_is_not_a_number_is_an_error(self, monkeypatch):
        monkeypatch.setenv("DISCORD_GUILD", "not-a-number")

        with pytest.raises(ValueError):
            guild_id()

    def test_the_admin_defaults_to_the_servers_admin(self, monkeypatch):
        assert admin_user_id() == DEFAULT_ADMIN_USER_ID
        monkeypatch.setenv("HALLYU_ID", "77")

        assert admin_user_id() == 77

    def test_a_blank_admin_id_uses_the_default(self, monkeypatch):
        monkeypatch.setenv("HALLYU_ID", "")

        assert admin_user_id() == DEFAULT_ADMIN_USER_ID

    def test_the_youtube_token_location(self, monkeypatch):
        assert youtube_token_path() is None
        monkeypatch.setenv("TOKEN_DIR", "/app/data/token.json")

        assert youtube_token_path() == "/app/data/token.json"

    @pytest.mark.parametrize("value, expected", [
        (None, "INFO"), ("DEBUG", "DEBUG"), ("debug", "DEBUG"), ("  warning ", "WARNING"), ("ERROR", "ERROR"),
        ("INFO", "INFO"), ("CRITICAL", "INFO"), ("verbose", "INFO"), ("", "INFO"),
    ])
    def test_the_log_level_falls_back_to_info_for_anything_unusable(self, monkeypatch, value, expected):
        if value is not None:
            monkeypatch.setenv("LOG_LEVEL", value)

        assert log_level() == expected


class TestDatabases:
    """Every database has a schema, a setting and a path."""

    def test_the_setting_is_named_after_the_database(self):
        assert Database.MERCH.env_var == "DB_PATH_MERCH"
        assert Database.HALL_OF_FAME.env_var == "DB_PATH_HALL_OF_FAME"

    def test_the_path_comes_from_the_setting_and_is_none_when_unset(self, monkeypatch):
        assert Database.MERCH.path is None
        monkeypatch.setenv("DB_PATH_MERCH", "/data/merch.db")

        assert Database.MERCH.path == "/data/merch.db"

    @pytest.mark.parametrize("database", list(Database), ids=lambda d: d.name)
    def test_every_database_has_a_schema_file(self, database):
        assert database.schema_path == SCHEMA_DIR / f"{database.value}.sql"
        assert database.schema_path.is_file()

    def test_there_are_eleven_databases_with_unique_settings(self):
        assert len(Database) == 11
        assert len({d.env_var for d in Database}) == 11

    def test_every_database_setting_is_provided_by_the_dockerfile(self):
        dockerfile = (SCHEMA_DIR.parent.parent.parent / "Dockerfile").read_text(encoding="utf-8")

        assert all(f"{database.env_var}=" in dockerfile for database in Database)


class TestNames:
    """The channel and role names the bot looks up."""

    def test_channel_names_are_lowercase_with_dashes(self):
        assert all(c.value == c.value.lower() and " " not in c.value for c in Channel)

    def test_the_names_are_plain_strings_so_they_can_be_compared_with_discords(self):
        assert Channel.LISTEN_GAME == "listen-game" and Role.LISTEN_GAME_GM == "Listen Game GM"

    def test_the_media_folder_is_next_to_the_code(self):
        assert MEDIA_DIR.is_dir() and (MEDIA_DIR / "gifs").is_dir() and (MEDIA_DIR / "images").is_dir()
