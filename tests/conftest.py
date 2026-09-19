"""Fixtures shared by every test. See "Testing" in CLAUDE.md for how they fit together.

Two kinds live here:

* Safety nets (autouse): every test starts with no configuration, and can't reach the real
  YouTube API or launch Chromium by accident.
* Tools tests ask for by name: temporary databases, a query helper, frozen time, and factories
  for the Discord objects the bot works with.
"""

import io
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest import mock

import pytest
from freezegun import freeze_time

from config import Database
from db.initialize import initialize_databases
from services import youtube
from testsupport import fakes
from ui import bracket_renderer

# Everything the bot reads from the environment (see config.py)
_CONFIG_VARIABLES = ("DISCORD_TOKEN", "DISCORD_GUILD", "HALLYU_ID", "TOKEN_DIR", "LOG_LEVEL")


# --- Safety nets -------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    """
    Starts every test with no bot configuration, so nothing can read a developer's real `.env` or
    write to a real database. Tests that need a setting call `monkeypatch.setenv` or `databases`.
    """
    for variable in _CONFIG_VARIABLES + tuple(db.env_var for db in Database):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture(autouse=True)
def _no_real_youtube(monkeypatch):
    """
    Fails loudly if a test reaches the real YouTube API. Patch the `services.youtube` function the
    code under test calls (in the module that imports it, e.g. `triggers.releases.add_video_to_playlist`).
    """
    def refuse():
        raise AssertionError("A test tried to use the real YouTube API; patch the services.youtube function.")

    monkeypatch.setattr(youtube, "get_yt_service", refuse)


@pytest.fixture(autouse=True)
def _no_real_browser(monkeypatch):
    """
    Stops a test launching Chromium. `render_html_to_image` catches the error and returns None, like a
    real rendering failure. Use `fake_bracket_render` when a test needs a picture back.
    """
    def refuse():
        raise AssertionError("A test tried to launch Chromium; use the fake_bracket_render fixture.")

    monkeypatch.setattr("ui.bracket_renderer._browser_cache.browser", refuse)


# --- Databases ---------------------------------------------------------------------------------

@pytest.fixture
def databases(tmp_path, monkeypatch) -> Callable[..., dict[Database, Path]]:
    """
    Factory that creates real, empty SQLite databases in a temporary folder and points the bot at them.

        def test_something(databases):
            databases(Database.MERCH, Database.LISTS)
            ...

    The schema and migrations are applied by the same `initialize_databases()` the bot runs at
    startup. A database that isn't requested stays unconfigured (calls to it raise
    `DatabaseNotConfiguredError`, as in production). Returns the file paths.
    """
    def create(*wanted: Database) -> dict[Database, Path]:
        paths = {db: tmp_path / f"{db.value}.db" for db in wanted}
        for db, path in paths.items():
            monkeypatch.setenv(db.env_var, str(path))
        initialize_databases()
        return paths

    return create


@pytest.fixture
def all_databases(request) -> dict[Database, Path]:
    """Every database, created and configured."""
    return request.getfixturevalue("databases")(*Database)


@pytest.fixture
def query() -> Callable[..., list[sqlite3.Row]]:
    """
    Reads a database directly, for checking what a function actually stored:

        rows = query(Database.MERCH, "SELECT balance FROM users WHERE user_id = ?", 5)
        assert rows[0]["balance"] == 10

    Rows can be indexed by column name or position. Use it to assert on state, and use `execute`
    to set it up.
    """
    def run(db: Database, sql: str, *params) -> list[sqlite3.Row]:
        conn = sqlite3.connect(db.path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    return run


@pytest.fixture
def execute() -> Callable[..., None]:
    """
    Writes to a database directly, to set up a starting state without going through the code under test:

        execute(Database.MERCH, "INSERT INTO users (user_id, balance) VALUES (?, ?)", 5, 100)
    """
    def run(db: Database, sql: str, *params) -> None:
        conn = sqlite3.connect(db.path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    return run


# --- Time --------------------------------------------------------------------------------------

@pytest.fixture
def frozen_time() -> Iterator[Callable[[str], object]]:
    """
    Freezes `datetime.now()` (and friends) at a UTC moment; call it again to move the clock:

        frozen_time("2026-12-01 05:00:00")   # midnight in Toronto, so the award year rolls over

    `datetime.now(tz)` converts from that UTC moment. It does not change SQLite's own
    CURRENT_TIMESTAMP, so insert explicit timestamps when a test depends on stored times.
    """
    freezers = []

    def freeze(moment: str):
        freezer = freeze_time(moment)
        freezer.start()
        freezers.append(freezer)
        return freezer

    yield freeze
    for freezer in reversed(freezers):
        freezer.stop()


# --- Discord objects ---------------------------------------------------------------------------

@pytest.fixture
def make_member() -> Callable[..., mock.MagicMock]:
    """Factory: `make_member(user_id=5, name="Jo", roles=("Listen Game GM",), administrator=True)`."""
    return fakes.make_member


@pytest.fixture
def make_channel() -> Callable[..., mock.MagicMock]:
    """Factory: `make_channel("merch-booth")`."""
    return fakes.make_channel


@pytest.fixture
def make_guild() -> Callable[..., mock.MagicMock]:
    """Factory: `make_guild(channels=("roles", "tournaments"), roles=("Trainee",))`."""
    return fakes.make_guild


@pytest.fixture
def make_interaction() -> Callable[..., mock.MagicMock]:
    """Factory: `make_interaction(channel="merch-booth", administrator=True)`; see `fakes.make_interaction`."""
    return fakes.make_interaction


@pytest.fixture
def make_message() -> Callable[..., mock.MagicMock]:
    """Factory: `make_message("hello", author=bot_member, channel="general")`."""
    return fakes.make_message


@pytest.fixture
def make_client() -> Callable[..., mock.MagicMock]:
    """Factory: `make_client(guild=guild)`, the bot as tasks and triggers see it."""
    return fakes.make_client


@pytest.fixture
def interaction() -> mock.MagicMock:
    """A ready-made interaction from an ordinary member in #general. Read what was sent from `.sent`."""
    return fakes.make_interaction()


@pytest.fixture
def admin_interaction() -> mock.MagicMock:
    """A ready-made interaction from a server administrator in #general."""
    return fakes.make_interaction(administrator=True)


# --- Other external services -------------------------------------------------------------------

@pytest.fixture
def fake_bracket_render(monkeypatch) -> mock.AsyncMock:
    """Makes bracket rendering return a tiny fake PNG instead of using Chromium; returns the mock to assert on."""
    async def render(*_, **__):
        return io.BytesIO(b"\x89PNG fake")

    fake = mock.AsyncMock(side_effect=render)
    monkeypatch.setattr(bracket_renderer, "render_html_to_image", fake)
    return fake
