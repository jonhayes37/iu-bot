"""Tests for tasks/secret_polls.py: closing polls, saying so publicly and sending the results privately."""

import logging
from datetime import datetime, timedelta, timezone
from unittest import mock

import discord
import pytest

from config import Database
from db.bot import (
    create_secret_poll, get_secret_poll, mark_secret_poll_closed, record_secret_vote, set_secret_poll_message
)
from tasks.secret_polls import close_secret_poll, close_secret_polls
from ui.secret_poll import SecretPollView

NOON = datetime(2026, 12, 12, 12, 0, 0, tzinfo=timezone.utc)
FORBIDDEN = discord.Forbidden(mock.Mock(status=403, reason="Forbidden"), "Cannot send messages to this user")


@pytest.fixture(autouse=True)
def _bot_database(databases, frozen_time):
    databases(Database.BOT)
    frozen_time("2026-12-13 12:00:01")       # just after a poll opened at NOON for 24 hours closes


@pytest.fixture(name="server")
def _server(make_guild, make_client, make_member):
    """The poll's channel and message, the admin who started it, and the bot."""
    guild = make_guild(channels=("announcements",))
    channel = guild.text_channels[0]
    message = mock.MagicMock(spec=discord.Message)
    message.edit = mock.AsyncMock()
    channel.fetch_message = mock.AsyncMock(return_value=message)
    admin = make_member(1, "admin")
    client = make_client(guild=guild)
    client.get_channel = mock.MagicMock(side_effect=lambda cid: channel if cid == channel.id else None)
    client.fetch_user = mock.AsyncMock(return_value=admin)
    return mock.Mock(channel=channel, message=message, admin=admin, client=client)


def _poll(server, closes_at=NOON + timedelta(hours=24), message_id=555):
    poll_id = create_secret_poll("Song of the Year tiebreaker", ["IVE - HEYA", "aespa - Supernova"], 1,
                                 server.channel.id, closes_at)
    if message_id:
        set_secret_poll_message(poll_id, message_id)
    return poll_id


async def test_a_poll_past_its_time_is_closed_publicly_and_the_results_go_only_to_the_admin(server):
    poll_id = _poll(server)
    for user_id, position in ((101, 0), (102, 0), (103, 1)):
        record_secret_vote(poll_id, user_id, position, NOON)

    await close_secret_polls.coro(server.client)

    assert get_secret_poll(poll_id).closed
    server.channel.fetch_message.assert_awaited_once_with(555)
    edit = server.message.edit.await_args.kwargs
    assert edit["embed"].description == "Voting has closed."
    assert edit["embed"].title == "🗳️ Song of the Year tiebreaker"
    assert isinstance(edit["view"], SecretPollView)
    assert all(button.item.disabled for button in edit["view"].children)
    [dm] = server.admin.sent
    assert dm.content.endswith("3 votes\n• IVE - HEYA: 2\n• aespa - Supernova: 1\n🏆 Winner: IVE - HEYA")
    assert server.channel.sent == []                 # nothing else is posted publicly


async def test_an_open_poll_is_left_alone(server):
    poll_id = _poll(server, closes_at=NOON + timedelta(days=2))

    await close_secret_polls.coro(server.client)

    assert not get_secret_poll(poll_id).closed
    server.message.edit.assert_not_awaited()
    assert server.admin.sent == []


async def test_a_poll_is_closed_and_reported_only_once(server):
    poll_id = _poll(server)
    poll = get_secret_poll(poll_id)

    await close_secret_poll(server.client, poll)
    await close_secret_poll(server.client, poll)          # e.g. two ticks racing
    await close_secret_polls.coro(server.client)

    assert len(server.admin.sent) == 1
    server.message.edit.assert_awaited_once()


async def test_an_already_closed_poll_is_not_reported_again(server):
    poll_id = _poll(server)
    mark_secret_poll_closed(poll_id)

    await close_secret_poll(server.client, get_secret_poll(poll_id))

    assert server.admin.sent == []


async def test_the_admin_is_found_in_the_cache_when_possible(server):
    _poll(server)
    server.client.get_user = mock.MagicMock(return_value=server.admin)

    await close_secret_polls.coro(server.client)

    server.client.fetch_user.assert_not_awaited()
    assert len(server.admin.sent) == 1


async def test_a_deleted_post_still_closes_the_poll_and_sends_the_results(server, caplog):
    poll_id = _poll(server)
    server.channel.fetch_message.side_effect = discord.NotFound(mock.Mock(status=404, reason="x"), "Unknown")

    with caplog.at_level(logging.WARNING, logger="iu-bot"):
        await close_secret_polls.coro(server.client)

    assert get_secret_poll(poll_id).closed
    assert len(server.admin.sent) == 1
    assert "could not mark the post closed" in caplog.text


@pytest.mark.parametrize("message_id, channel_known", [(None, True), (555, False)])
async def test_a_poll_whose_post_or_channel_is_gone_still_sends_the_results(server, caplog, message_id,
                                                                            channel_known):
    _poll(server, message_id=message_id)
    if not channel_known:
        server.client.get_channel = mock.MagicMock(return_value=None)

    with caplog.at_level(logging.WARNING, logger="iu-bot"):
        await close_secret_polls.coro(server.client)

    server.message.edit.assert_not_awaited()
    assert len(server.admin.sent) == 1
    assert "its post is gone" in caplog.text


async def test_if_the_admin_cannot_be_messaged_the_poll_still_closes(server, caplog):
    poll_id = _poll(server)
    server.admin.send.side_effect = FORBIDDEN

    with caplog.at_level(logging.WARNING, logger="iu-bot"):
        await close_secret_polls.coro(server.client)

    assert get_secret_poll(poll_id).closed
    server.message.edit.assert_awaited_once()
    assert "could not DM the results" in caplog.text


async def test_one_failing_poll_does_not_stop_the_others(server, monkeypatch, caplog):
    first, second = _poll(server), _poll(server)
    real_close = close_secret_poll

    async def close_or_fail(client, poll):
        if poll.poll_id == first:
            raise RuntimeError("boom")
        await real_close(client, poll)
    monkeypatch.setattr("tasks.secret_polls.close_secret_poll", close_or_fail)

    with caplog.at_level(logging.ERROR, logger="iu-bot"):
        await close_secret_polls.coro(server.client)

    assert get_secret_poll(second).closed and not get_secret_poll(first).closed
    assert f"Secret poll {first}: failed to close." in caplog.text
