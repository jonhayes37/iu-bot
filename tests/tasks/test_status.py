"""Tests for tasks/status.py: IU's "Listening to" status follows the saved one, and expires."""

from unittest import mock

import discord
import pytest

from config import Database
from db.bot import save_bot_status_db
from tasks.status import refresh_status, show_saved_status


@pytest.fixture(autouse=True)
def _bot_database(databases, frozen_time):
    databases(Database.BOT)
    frozen_time("2026-03-17 12:00:00")


@pytest.fixture(name="client")
def _client():
    client = mock.Mock(spec=discord.Client)
    client.change_presence = mock.AsyncMock()
    return client


def _save(execute, text, days, created_at="2026-03-17 11:00:00"):
    # The save time comes from SQLite's own clock, so pin it to the test clock
    save_bot_status_db(text, days)
    execute(Database.BOT, "UPDATE statuses SET created_at = ?", created_at)


def _shown(client):
    activity = client.change_presence.await_args.kwargs["activity"]
    return None if activity is None else (activity.type, activity.name)


async def test_a_saved_status_is_shown_as_listening(client, execute):
    _save(execute, "Good Day", 7)

    await show_saved_status(client)

    assert client.change_presence.await_args.kwargs["status"] is discord.Status.online
    assert _shown(client) == (discord.ActivityType.listening, "Good Day")


async def test_with_no_saved_status_there_is_none(client):
    await show_saved_status(client)

    client.change_presence.assert_awaited_once_with(status=discord.Status.online, activity=None)


async def test_a_cleared_status_shows_none(client, execute):
    _save(execute, "", 7)

    await show_saved_status(client)

    assert _shown(client) is None


async def test_the_hourly_refresh_takes_down_a_status_once_it_expires(client, execute, frozen_time):
    _save(execute, "Good Day", 1)
    await refresh_status.coro(client)
    assert _shown(client) == (discord.ActivityType.listening, "Good Day")

    frozen_time("2026-03-18 12:00:00")          # a day and an hour after it was set
    await refresh_status.coro(client)

    assert _shown(client) is None


async def test_runs_every_hour():
    assert refresh_status.hours == 1


async def test_a_failure_is_logged_and_the_loop_keeps_running(client, caplog):
    client.change_presence.side_effect = RuntimeError("gateway closed")

    await refresh_status.coro(client)

    assert "Unhandled error in refresh_status" in caplog.text
