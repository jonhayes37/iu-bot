"""Tests for tasks/listen_game.py: the hourly Listen Game check (reveals, deadlines and reminders)."""

import logging
from datetime import datetime, timedelta, timezone
from unittest import mock

import discord
import pytest

from config import Channel, Database
from db.listen_game import (
    PendingPlayer, RoundStatus, get_current_round_db, get_missing_players_for_reminders_db, get_round_db,
    set_round_theme_db, update_round_playlist_db, update_round_ruleset_message_db, upsert_submission_db
)
from tasks.listen_game import (
    FIRST_REMINDER_AFTER, REMINDER_EVERY, _reminder_due, check_listen_game_reminders
)
from testsupport.listen_game import reveal_ready_round, start_game

NOW = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
HOST, PLAYER_A, PLAYER_B = 101, 102, 103


@pytest.fixture(autouse=True)
def _listen_game_database(databases, frozen_time):
    databases(Database.LISTEN_GAME)
    frozen_time("2026-03-17 12:00:00")


@pytest.fixture(name="server")
def _server(make_guild, make_client, make_member, monkeypatch):
    """The server with #listen-game, the three players as DM-able members, and the reveal starter mocked."""
    guild = make_guild(channels=(Channel.LISTEN_GAME,))
    members = {uid: make_member(user_id=uid, name=f"Player {uid}") for uid in (HOST, PLAYER_A, PLAYER_B)}
    client = make_client(guild=guild)
    client.get_user.side_effect = members.get
    start_reveal = mock.Mock(return_value=True)
    monkeypatch.setattr("tasks.listen_game.start_reveal", start_reveal)
    return mock.Mock(guild=guild, channel=guild.text_channels[0], client=client, members=members,
                     start_reveal=start_reveal)


async def _tick(server):
    await check_listen_game_reminders.coro(server.client, server.guild.id)


def _hours_ago(hours):
    return (NOW - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def _open_round(execute, *, started_hours_ago, max_round_days=None):
    """A round whose theme was set `started_hours_ago` hours ago. Returns (game_id, round_id)."""
    game_id = start_game((HOST, PLAYER_A, PLAYER_B), max_round_days)
    round_id = get_current_round_db(game_id).round_id
    set_round_theme_db(round_id, "Rain songs")
    execute(Database.LISTEN_GAME, "UPDATE listen_rounds SET started_at = ? WHERE round_id = ?",
            _hours_ago(started_hours_ago), round_id)
    return game_id, round_id


def _dms(server, user_id):
    return [message.content for message in server.members[user_id].sent]


class TestSetup:
    """The task needs the server and its channel."""

    async def test_runs_every_hour(self):
        assert check_listen_game_reminders.hours == 1

    @pytest.mark.parametrize("guild_id", [None, 0])
    async def test_no_guild_id_is_reported(self, make_client, caplog, guild_id):
        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await check_listen_game_reminders.coro(make_client(), guild_id)

        assert "guild_id is not set" in caplog.text

    async def test_an_unknown_guild_is_reported(self, make_client, caplog):
        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await check_listen_game_reminders.coro(make_client(), 999)

        assert "Could not find guild with ID: 999" in caplog.text

    async def test_a_server_without_the_game_channel_is_reported_and_nothing_else_runs(
            self, make_guild, make_client, monkeypatch, caplog):
        guild = make_guild(channels=("general",))
        start_reveal = mock.Mock()
        monkeypatch.setattr("tasks.listen_game.start_reveal", start_reveal)
        reveal_ready_round(start_game())

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await check_listen_game_reminders.coro(make_client(guild=guild), guild.id)

        assert "Could not find #listen-game channel" in caplog.text
        start_reveal.assert_not_called()

    async def test_an_error_in_one_check_does_not_stop_the_task(self, server, monkeypatch, caplog):
        monkeypatch.setattr("tasks.listen_game.get_revealing_round_ids_db", mock.Mock(side_effect=OSError("disk")))

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await _tick(server)

        assert "Unhandled error in check_listen_game_reminders" in caplog.text


class TestInterruptedReveals:
    """A reveal cut short by a restart is picked up again."""

    async def test_a_round_being_revealed_is_resumed_in_the_game_channel(self, server):
        round_id = reveal_ready_round(start_game())

        await _tick(server)

        server.start_reveal.assert_called_once_with(server.channel, round_id)

    async def test_nothing_is_resumed_when_no_round_is_being_revealed(self, server, execute):
        _open_round(execute, started_hours_ago=1)

        await _tick(server)

        server.start_reveal.assert_not_called()

    async def test_a_reveal_that_is_already_running_is_left_alone(self, server, caplog):
        reveal_ready_round(start_game())
        server.start_reveal.return_value = False

        with caplog.at_level(logging.INFO, logger="iu-bot"):
            await _tick(server)

        assert "Resuming the reveal" not in caplog.text

    async def test_a_resumed_reveal_is_logged(self, server, caplog):
        round_id = reveal_ready_round(start_game())

        with caplog.at_level(logging.INFO, logger="iu-bot"):
            await _tick(server)

        assert f"Resuming the reveal for round {round_id}" in caplog.text


class TestDeadlines:
    """A round past its deadline is locked and its listener is told."""

    async def test_an_overdue_round_is_locked_and_the_listener_is_told(self, server, execute):
        _, round_id = _open_round(execute, started_hours_ago=49, max_round_days=2)
        update_round_playlist_db(round_id, "PLabc")

        await _tick(server)

        assert get_round_db(round_id).status is RoundStatus.RANKING
        [dm] = _dms(server, HOST)
        assert dm.startswith("⏰ **Time's Up!**")
        assert "https://www.youtube.com/playlist?list=PLabc" in dm
        assert "`/listen-game-submit-ranking`" in dm

    async def test_a_round_without_a_playlist_says_so(self, server, execute):
        _open_round(execute, started_hours_ago=49, max_round_days=2)

        await _tick(server)

        assert "No playlist generated." in _dms(server, HOST)[0]

    async def test_a_round_still_inside_its_deadline_is_left_open(self, server, execute):
        _, round_id = _open_round(execute, started_hours_ago=47, max_round_days=2)

        await _tick(server)

        assert get_round_db(round_id).status is RoundStatus.SUBMITTING
        assert _dms(server, HOST) == []

    async def test_a_game_without_a_deadline_never_times_out(self, server, execute):
        _, round_id = _open_round(execute, started_hours_ago=24 * 30, max_round_days=None)

        await _tick(server)

        assert get_round_db(round_id).status is RoundStatus.SUBMITTING

    async def test_a_listener_with_closed_dms_still_has_the_round_locked(self, server, execute, caplog):
        _, round_id = _open_round(execute, started_hours_ago=49, max_round_days=2)
        server.members[HOST].send.side_effect = discord.Forbidden(mock.Mock(status=403, reason="x"), "closed")

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await _tick(server)

        assert get_round_db(round_id).status is RoundStatus.RANKING
        assert "Could not DM user 101" in caplog.text


class TestReminderTiming:
    """A player is reminded after 48 hours, then once a day until they submit."""

    @staticmethod
    def _player(started_hours_ago, reminded_hours_ago=None):
        return PendingPlayer(user_id=1, game_id=1, round_id=1, started_at=_hours_ago(started_hours_ago),
                             last_reminded_at=None if reminded_hours_ago is None else _hours_ago(reminded_hours_ago))

    @pytest.mark.parametrize("started, reminded, due", [
        (1, None, False),
        (47, None, False),
        (48, None, True),           # exactly 48 hours: due
        (49, None, True),
        (72, 1, False),             # reminded an hour ago
        (72, 23, False),
        (72, 24, True),             # exactly a day since the last one
        (72, 30, True),
        (47, 30, False),            # a reminder can't be due before the 48-hour mark
    ])
    def test_when_a_reminder_is_due(self, started, reminded, due):
        assert _reminder_due(self._player(started, reminded), NOW) is due

    def test_the_intervals_are_two_days_then_daily(self):
        assert FIRST_REMINDER_AFTER == timedelta(hours=48)
        assert REMINDER_EVERY == timedelta(hours=24)


class TestReminders:
    """The reminder DMs."""

    async def test_players_who_owe_a_song_are_reminded_but_not_the_listener(self, server, execute):
        _open_round(execute, started_hours_ago=50)

        await _tick(server)

        assert len(_dms(server, PLAYER_A)) == 1 and len(_dms(server, PLAYER_B)) == 1
        assert _dms(server, HOST) == []

    async def test_the_reminder_points_to_the_ruleset_post(self, server, execute):
        _, round_id = _open_round(execute, started_hours_ago=50)
        update_round_ruleset_message_db(round_id, 5551)

        await _tick(server)

        dm = _dms(server, PLAYER_A)[0]
        assert dm.startswith("🎧 **Listen Game Reminder!**")
        assert f"https://discord.com/channels/{server.guild.id}/{server.channel.id}/5551" in dm
        assert "`/listen-game-submit-song`" in dm

    async def test_without_a_ruleset_post_it_links_the_channel(self, server, execute):
        _open_round(execute, started_hours_ago=50)

        await _tick(server)

        assert f"**[#listen-game](<{server.channel.jump_url}>)**" in _dms(server, PLAYER_A)[0]

    async def test_a_deadline_is_shown_when_the_game_has_one(self, server, execute):
        _open_round(execute, started_hours_ago=50, max_round_days=5)
        deadline = int((NOW - timedelta(hours=50) + timedelta(days=5)).timestamp())

        await _tick(server)

        assert f"⏰ **Automated Deadline:** <t:{deadline}:R> (<t:{deadline}:f>)" in _dms(server, PLAYER_A)[0]

    async def test_no_deadline_line_for_a_game_without_one(self, server, execute):
        _open_round(execute, started_hours_ago=50)

        await _tick(server)

        assert "Automated Deadline" not in _dms(server, PLAYER_A)[0]

    async def test_a_round_less_than_two_days_old_sends_nothing(self, server, execute):
        _open_round(execute, started_hours_ago=47)

        await _tick(server)

        assert _dms(server, PLAYER_A) == [] and _dms(server, PLAYER_B) == []

    async def test_a_player_who_has_submitted_is_not_reminded(self, server, execute):
        _, round_id = _open_round(execute, started_hours_ago=50)
        upsert_submission_db(round_id, PLAYER_A, "vid1", "Song")

        await _tick(server)

        assert _dms(server, PLAYER_A) == [] and len(_dms(server, PLAYER_B)) == 1

    async def test_a_sent_reminder_is_recorded_so_the_next_hour_does_not_repeat_it(self, server, execute):
        _open_round(execute, started_hours_ago=50)

        await _tick(server)
        await _tick(server)

        assert len(_dms(server, PLAYER_A)) == 1
        assert all(p.last_reminded_at for p in get_missing_players_for_reminders_db())

    async def test_a_day_later_the_player_is_reminded_again(self, server, execute, frozen_time):
        _open_round(execute, started_hours_ago=50)
        await _tick(server)
        # The reminder time is stamped by SQLite's own clock, which the frozen clock doesn't change
        execute(Database.LISTEN_GAME, "UPDATE listen_players SET last_reminded_at = ?", _hours_ago(0))

        frozen_time("2026-03-18 12:00:00")
        await _tick(server)

        assert len(_dms(server, PLAYER_A)) == 2

    async def test_a_failed_dm_is_not_recorded_so_it_is_tried_again_next_hour(self, server, execute):
        _open_round(execute, started_hours_ago=50)
        server.members[PLAYER_A].send.side_effect = discord.Forbidden(mock.Mock(status=403, reason="x"), "closed")

        await _tick(server)

        reminded = {p.user_id: p.last_reminded_at for p in get_missing_players_for_reminders_db()}
        assert reminded[PLAYER_A] is None and reminded[PLAYER_B] is not None

    async def test_one_failed_dm_does_not_stop_the_others(self, server, execute):
        _open_round(execute, started_hours_ago=50)
        server.members[PLAYER_A].send.side_effect = discord.HTTPException(mock.Mock(status=500, reason="x"), "boom")

        await _tick(server)

        assert len(_dms(server, PLAYER_B)) == 1

    async def test_no_reminders_after_submissions_have_closed(self, server, execute):
        _, round_id = _open_round(execute, started_hours_ago=50)
        execute(Database.LISTEN_GAME, "UPDATE listen_rounds SET status = 'ranking' WHERE round_id = ?", round_id)

        await _tick(server)

        assert _dms(server, PLAYER_A) == []
