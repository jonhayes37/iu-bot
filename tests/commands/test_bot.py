"""Tests for commands/bot.py: /set-status."""

import discord
import pytest

from commands.bot import MAX_STATUS_DAYS, MAX_STATUS_LENGTH, set_iu_status
from config import Channel, Database
from db.bot import get_active_bot_status_db


@pytest.fixture(autouse=True)
def _bot_database(databases, frozen_time):
    databases(Database.BOT)
    frozen_time("2026-03-17 12:00:00")


async def test_only_works_in_the_sandbox_and_changes_nothing_elsewhere(make_interaction):
    interaction = make_interaction(channel="general", administrator=True)

    await set_iu_status.callback(interaction, "Listening to IU", 7)

    assert interaction.sent[0].content == "This command can only be used in the #sandbox channel."
    assert get_active_bot_status_db() is None
    interaction.client.change_presence.assert_not_awaited()


async def test_sets_a_listening_status_and_saves_it_for_reconnections(make_interaction):
    interaction = make_interaction(channel=Channel.SANDBOX, administrator=True)

    await set_iu_status.callback(interaction, "Good Day", 3)

    assert get_active_bot_status_db() == "Good Day"
    kwargs = interaction.client.change_presence.await_args.kwargs
    assert kwargs["status"] is discord.Status.online
    assert (kwargs["activity"].type, kwargs["activity"].name) == (discord.ActivityType.listening, "Good Day")
    [reply] = interaction.sent
    assert reply.content == "✅ IU's status has been updated to `Good Day` and will expire in 3 days."
    assert not reply.ephemeral


async def test_the_status_lasts_a_week_by_default(make_interaction, execute, frozen_time):
    interaction = make_interaction(channel=Channel.SANDBOX, administrator=True)

    await set_iu_status.callback(interaction, "Good Day")

    assert "expire in 7 days" in interaction.sent[0].content
    # The save time comes from SQLite's own clock, so pin it to the test clock
    execute(Database.BOT, "UPDATE statuses SET created_at = '2026-03-17 12:00:00'")
    frozen_time("2026-03-24 11:59:00")
    assert get_active_bot_status_db() == "Good Day"
    frozen_time("2026-03-24 12:01:00")
    assert get_active_bot_status_db() is None


async def test_leaving_the_text_out_clears_the_status_and_the_clear_is_saved(make_interaction):
    await set_iu_status.callback(make_interaction(channel=Channel.SANDBOX, administrator=True), "Good Day")
    interaction = make_interaction(channel=Channel.SANDBOX, administrator=True)

    await set_iu_status.callback(interaction)

    interaction.client.change_presence.assert_awaited_once_with(status=discord.Status.online, activity=None)
    assert interaction.sent[0].content == "✅ IU's status has been cleared!"
    assert get_active_bot_status_db() == ""


async def test_the_newest_status_replaces_the_previous_one(make_interaction, execute):
    execute(Database.BOT, "INSERT INTO statuses (status_text, max_duration_days, created_at) "
                          "VALUES ('old', 7, '2026-03-16 00:00:00')")
    interaction = make_interaction(channel=Channel.SANDBOX, administrator=True)

    await set_iu_status.callback(interaction, "new", 7)
    execute(Database.BOT, "UPDATE statuses SET created_at = '2026-03-17 12:00:00' WHERE status_text = 'new'")

    assert get_active_bot_status_db() == "new"


def test_the_options_are_limited_to_what_discord_shows_and_a_sensible_expiry():
    options = {p.name: p for p in set_iu_status.parameters}

    assert not options["status_text"].required
    assert (options["status_text"].min_value, options["status_text"].max_value) == (1, MAX_STATUS_LENGTH)
    assert (options["days"].min_value, options["days"].max_value) == (1, MAX_STATUS_DAYS)
    assert MAX_STATUS_LENGTH == 128
