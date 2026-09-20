"""Tests for tasks/scheduled_events.py: the thread opened 15 minutes before a community event."""

import logging
from datetime import datetime, timedelta, timezone
from unittest import mock

import discord
import pytest

from config import Channel
from tasks import scheduled_events
from tasks.scheduled_events import check_upcoming_events, notified_events

NOW = datetime(2026, 3, 17, 18, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fixed_clock(frozen_time):
    frozen_time("2026-03-17 18:00:00")
    notified_events.clear()
    yield
    notified_events.clear()


@pytest.fixture(name="server")
def _server(make_guild, make_client, make_member):
    """The server with a #community-events channel, its thread factory, and the bot's client."""
    guild = make_guild(channels=(Channel.COMMUNITY_EVENTS,))
    thread = mock.MagicMock(spec=discord.Thread)
    thread.send = mock.AsyncMock()
    guild.text_channels[0].create_thread = mock.AsyncMock(return_value=thread)
    client = make_client(guild=guild)
    return mock.Mock(guild=guild, channel=guild.text_channels[0], thread=thread, client=client,
                     fan=make_member(user_id=1, name="Fan"), other_fan=make_member(user_id=2, name="Other"))


async def _tick(server):
    await check_upcoming_events.coro(server.client, server.guild.id)


class TestSetup:
    """The task needs the server and its channel."""

    async def test_runs_every_minute(self):
        assert check_upcoming_events.minutes == 1

    @pytest.mark.parametrize("guild_id", [None, 0])
    async def test_no_guild_id_is_reported(self, make_client, caplog, guild_id):
        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await check_upcoming_events.coro(make_client(), guild_id)

        assert "guild_id is not set" in caplog.text

    async def test_an_unknown_guild_is_reported(self, make_client, caplog):
        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await check_upcoming_events.coro(make_client(), 999)

        assert "Could not find guild with ID: 999" in caplog.text

    async def test_a_server_without_the_events_channel_is_reported(self, make_guild, make_client, caplog):
        guild = make_guild(channels=("general",))
        guild.scheduled_events = [mock.Mock()]

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await check_upcoming_events.coro(make_client(guild=guild), guild.id)

        assert "Could not find #community-events channel" in caplog.text


class TestWhichEventsAreNotified:
    """Only a scheduled event that starts within 15 minutes, once."""

    async def test_an_event_starting_soon_gets_a_thread(self, server, make_scheduled_event):
        server.guild.scheduled_events = [make_scheduled_event("Watch Party", NOW + timedelta(minutes=10),
                                                              attendees=(server.fan,))]

        await _tick(server)

        server.channel.create_thread.assert_awaited_once()

    @pytest.mark.parametrize("minutes, notified", [(16, False), (15, True), (14, True), (1, True), (-5, True)])
    async def test_the_fifteen_minute_boundary(self, server, make_scheduled_event, minutes, notified):
        # An event whose start time has passed but that is still 'scheduled' is included
        server.guild.scheduled_events = [make_scheduled_event("Watch Party", NOW + timedelta(minutes=minutes),
                                                              attendees=(server.fan,))]

        await _tick(server)

        assert server.channel.create_thread.await_count == (1 if notified else 0)

    @pytest.mark.parametrize("status", [discord.EventStatus.active, discord.EventStatus.completed,
                                        discord.EventStatus.cancelled])
    async def test_events_that_are_not_waiting_to_start_are_skipped(self, server, make_scheduled_event, status):
        server.guild.scheduled_events = [make_scheduled_event("Watch Party", NOW + timedelta(minutes=5),
                                                              attendees=(server.fan,), status=status)]

        await _tick(server)

        server.channel.create_thread.assert_not_awaited()

    async def test_an_event_is_only_announced_once(self, server, make_scheduled_event):
        server.guild.scheduled_events = [make_scheduled_event("Watch Party", NOW + timedelta(minutes=5),
                                                              attendees=(server.fan,))]

        await _tick(server)
        await _tick(server)

        assert server.channel.create_thread.await_count == 1

    async def test_several_events_are_each_handled(self, server, make_scheduled_event):
        server.guild.scheduled_events = [
            make_scheduled_event("First", NOW + timedelta(minutes=5), attendees=(server.fan,)),
            make_scheduled_event("Second", NOW + timedelta(minutes=8), attendees=(server.fan,)),
            make_scheduled_event("Much later", NOW + timedelta(hours=3), attendees=(server.fan,))]

        await _tick(server)

        assert [c.kwargs["name"] for c in server.channel.create_thread.await_args_list] == ["First", "Second"]


class TestTheThread:
    """What is posted for an event."""

    async def test_a_public_thread_that_archives_after_a_day(self, server, make_scheduled_event):
        server.guild.scheduled_events = [make_scheduled_event("Watch Party", NOW + timedelta(minutes=5),
                                                              attendees=(server.fan,))]

        await _tick(server)

        server.channel.create_thread.assert_awaited_once_with(
            name="Watch Party", type=discord.ChannelType.public_thread, auto_archive_duration=1440)

    async def test_the_attendees_are_mentioned(self, server, make_scheduled_event):
        server.guild.scheduled_events = [make_scheduled_event(
            "Watch Party", NOW + timedelta(minutes=5), attendees=(server.fan, server.other_fan))]

        await _tick(server)

        content = server.thread.send.await_args.kwargs["content"]
        assert content == f"**Watch Party** is starting soon!\n\n{server.fan.mention} {server.other_fan.mention}"

    async def test_bots_are_not_mentioned(self, server, make_scheduled_event, make_member):
        robot = make_member(user_id=99, name="Robot", bot=True)
        server.guild.scheduled_events = [make_scheduled_event(
            "Watch Party", NOW + timedelta(minutes=5), attendees=(robot, server.fan))]

        await _tick(server)

        content = server.thread.send.await_args.kwargs["content"]
        assert server.fan.mention in content and robot.mention not in content

    async def test_an_event_nobody_is_going_to_gets_no_thread(self, server, make_scheduled_event, make_member):
        robot = make_member(user_id=99, name="Robot", bot=True)
        server.guild.scheduled_events = [
            make_scheduled_event("Empty", NOW + timedelta(minutes=5)),
            make_scheduled_event("Only a bot", NOW + timedelta(minutes=5), attendees=(robot,))]

        await _tick(server)

        server.channel.create_thread.assert_not_awaited()

    async def test_at_most_50_attendees_are_read(self, server, make_scheduled_event, make_member):
        crowd = tuple(make_member(user_id=1000 + i, name=f"Fan {i}") for i in range(60))
        server.guild.scheduled_events = [make_scheduled_event("Big Party", NOW + timedelta(minutes=5),
                                                              attendees=crowd)]

        await _tick(server)

        assert server.thread.send.await_args.kwargs["content"].count("<@") == 50

    async def test_long_event_names_are_shortened_to_discords_100_character_limit(self, server,
                                                                                  make_scheduled_event):
        server.guild.scheduled_events = [make_scheduled_event("N" * 150, NOW + timedelta(minutes=5),
                                                              attendees=(server.fan,))]

        await _tick(server)

        name = server.channel.create_thread.await_args.kwargs["name"]
        assert name == "N" * 97 + "..." and len(name) == 100

    async def test_a_100_character_name_is_left_alone(self, server, make_scheduled_event):
        server.guild.scheduled_events = [make_scheduled_event("N" * 100, NOW + timedelta(minutes=5),
                                                              attendees=(server.fan,))]

        await _tick(server)

        assert server.channel.create_thread.await_args.kwargs["name"] == "N" * 100

    async def test_the_events_gif_is_attached(self, server, make_scheduled_event):
        server.guild.scheduled_events = [make_scheduled_event("Watch Party", NOW + timedelta(minutes=5),
                                                              attendees=(server.fan,))]

        await _tick(server)

        assert server.thread.send.await_args.kwargs["file"].filename == "iu_event_thread.gif"

    async def test_without_the_gif_the_thread_still_gets_its_message(self, server, make_scheduled_event, tmp_path,
                                                                      monkeypatch, caplog):
        monkeypatch.setattr(scheduled_events, "MEDIA_DIR", tmp_path)
        server.guild.scheduled_events = [make_scheduled_event("Watch Party", NOW + timedelta(minutes=5),
                                                              attendees=(server.fan,))]

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await _tick(server)

        assert "file" not in server.thread.send.await_args.kwargs
        assert "Event GIF not found" in caplog.text
        assert len(notified_events) == 1


class TestFailures:
    """A problem with one event must not stop the others or leave it unannounced forever."""

    async def test_missing_permissions_are_logged_and_the_event_is_retried_next_tick(
            self, server, make_scheduled_event, caplog):
        server.guild.scheduled_events = [make_scheduled_event("Watch Party", NOW + timedelta(minutes=5),
                                                              attendees=(server.fan,))]
        server.channel.create_thread.side_effect = discord.Forbidden(mock.Mock(status=403, reason="x"), "no")

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await _tick(server)

        assert "lacks permissions to create threads" in caplog.text
        assert not notified_events
        server.channel.create_thread.side_effect = None
        await _tick(server)
        assert len(notified_events) == 1

    async def test_an_unexpected_error_is_logged_and_the_next_event_is_still_handled(
            self, server, make_scheduled_event, caplog):
        server.guild.scheduled_events = [
            make_scheduled_event("Broken", NOW + timedelta(minutes=5), attendees=(server.fan,)),
            make_scheduled_event("Fine", NOW + timedelta(minutes=6), attendees=(server.fan,))]
        server.channel.create_thread.side_effect = [RuntimeError("boom"), server.thread]

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await _tick(server)

        assert "Failed to process event warning for Broken: boom" in caplog.text
        assert server.channel.create_thread.await_count == 2
        assert len(notified_events) == 1
