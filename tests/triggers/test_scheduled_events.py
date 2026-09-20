"""Tests for triggers/scheduled_events.py: the duration prefix and the new-event announcement."""

import datetime
import logging
from unittest import mock

import discord
import pytest

from config import Channel, Role
from triggers.scheduled_events import _parse_duration, process_event

START = datetime.datetime(2026, 3, 20, 20, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture(name="make_event")
def _make_event(make_guild, make_member):
    """Builds an event in a server that has #community-events and the Watch Parties role."""
    def build(description, *, guild=None):
        server = guild or make_guild(channels=(Channel.COMMUNITY_EVENTS,), roles=(Role.WATCH_PARTIES,))
        event = mock.MagicMock(spec=discord.ScheduledEvent)
        event.name = "Movie Night"
        event.description = description
        event.start_time = START
        event.end_time = None
        event.guild = server
        event.creator = make_member(user_id=7, name="Host")
        event.url = "https://discord.com/events/1/2"
        event.edit = mock.AsyncMock()
        return event

    return build


class TestParseDuration:
    """Reading '1h 30m' style durations."""

    @pytest.mark.parametrize("text, hours, minutes", [
        ("1h 30m", 1, 30), ("1h", 1, 0), ("30m", 0, 30), ("2 hours", 2, 0), ("45 mins", 0, 45),
        ("1 hour 15 minutes", 1, 15), ("90m", 0, 90), ("3H", 3, 0), ("2h30", 2, 0), ("1h45m extra", 1, 45),
    ])
    def test_hours_and_minutes(self, text, hours, minutes):
        assert _parse_duration(text) == datetime.timedelta(hours=hours, minutes=minutes)

    @pytest.mark.parametrize("text", ["", "soon", "tonight", "0h", "0m", "0h 0m", "1 day"])
    def test_anything_without_a_positive_duration_is_none(self, text):
        assert _parse_duration(text) is None


class TestDurationPrefix:
    """A description starting with [1h 30m] sets the event's end time."""

    async def test_the_end_time_is_set_and_the_prefix_removed(self, make_event):
        event = make_event("[1h 30m] Bring snacks")

        await process_event(event, is_update=True)

        event.edit.assert_awaited_once_with(
            description="Bring snacks", end_time=START + datetime.timedelta(hours=1, minutes=30),
            reason="Parsed and enforced duration prefix from description.")

    async def test_a_multi_line_description_keeps_everything_after_the_prefix(self, make_event):
        event = make_event("[2h]\nLine one\nLine two")

        await process_event(event, is_update=True)

        assert event.edit.await_args.kwargs["description"] == "Line one\nLine two"

    @pytest.mark.parametrize("description", [None, "", "No prefix here", "[soon] Bring snacks", "[0h] Nope",
                                             "Bring snacks [1h]", " [1h] leading space"])
    async def test_descriptions_without_a_valid_prefix_are_left_alone(self, make_event, description):
        event = make_event(description)

        await process_event(event, is_update=True)

        event.edit.assert_not_awaited()

    async def test_an_update_never_announces(self, make_event):
        event = make_event("[1h] Bring snacks")

        await process_event(event, is_update=True)

        assert event.guild.text_channels[0].sent == []

    async def test_missing_permission_is_logged(self, make_event, caplog):
        event = make_event("[1h] x")
        event.edit.side_effect = discord.Forbidden(mock.Mock(status=403, reason="x"), "no")

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await process_event(event, is_update=True)

        assert "lacks 'Manage Events' permission" in caplog.text

    async def test_a_discord_error_is_logged_and_does_not_stop_the_announcement(self, make_event, caplog):
        event = make_event("[1h] x")
        event.edit.side_effect = discord.HTTPException(mock.Mock(status=500, reason="x"), "boom")

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await process_event(event, is_update=False)

        assert "Failed to update event duration" in caplog.text
        assert len(event.guild.text_channels[0].sent) == 1


class TestAnnouncement:
    """A newly created event is announced to the Watch Parties role."""

    async def test_announces_the_event_with_its_creator_and_link(self, make_event):
        event = make_event("Just a description")

        await process_event(event, is_update=False)

        [post] = event.guild.text_channels[0].sent
        assert post.content == (f"{event.guild.roles[0].mention} **Movie Night** has been scheduled by "
                                f"{event.creator.mention}! RSVP below so you don't miss out!\n\n{event.url}")

    async def test_a_new_event_with_a_duration_is_both_updated_and_announced(self, make_event):
        event = make_event("[1h] Bring snacks")

        await process_event(event, is_update=False)

        event.edit.assert_awaited_once()
        assert len(event.guild.text_channels[0].sent) == 1

    async def test_a_server_without_the_events_channel_is_reported(self, make_event, make_guild, caplog):
        event = make_event("x", guild=make_guild(channels=("general",), roles=(Role.WATCH_PARTIES,)))

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await process_event(event, is_update=False)

        assert "Could not find #community-events channel" in caplog.text

    async def test_a_server_without_the_role_is_reported_and_nothing_is_posted(self, make_event, make_guild, caplog):
        guild = make_guild(channels=(Channel.COMMUNITY_EVENTS,), roles=())
        event = make_event("x", guild=guild)

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await process_event(event, is_update=False)

        assert "Could not find Watch Parties role" in caplog.text
        assert guild.text_channels[0].sent == []
