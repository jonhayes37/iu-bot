"""Tests for commands/secret_poll.py: posting a secret poll and privately reading its results."""

from datetime import datetime, timedelta, timezone
from unittest import mock

import discord
import pytest

from commands.secret_poll import MAX_OPTION_LENGTH, MAX_OPTIONS, _poll_autocomplete, secret_poll, secret_poll_results
from config import Database
from db.bot import (
    SecretPoll, create_secret_poll, get_recent_secret_polls, get_secret_poll, get_secret_poll_options,
    mark_secret_poll_closed, record_secret_vote
)
from ui.secret_poll import SecretPollView

NOON = datetime(2026, 12, 12, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _bot_database(databases, frozen_time):
    databases(Database.BOT)
    frozen_time("2026-12-12 12:00:00")


class TestSecretPoll:
    """/secret-poll posts the poll in the channel and remembers it."""

    async def test_posts_a_button_per_option_and_tells_the_admin_privately(self, admin_interaction):
        await secret_poll.callback(admin_interaction, "Song of the Year tiebreaker", " IVE - HEYA | aespa - Supernova ")

        [poll] = get_recent_secret_polls()
        assert poll == SecretPoll(poll.poll_id, "Song of the Year tiebreaker", admin_interaction.user.id,
                                  admin_interaction.channel.id, poll.message_id, NOON + timedelta(hours=24), False)
        assert poll.message_id is not None
        assert get_secret_poll_options(poll.poll_id) == ["IVE - HEYA", "aespa - Supernova"]
        [post] = admin_interaction.channel.sent
        assert post.embed.title == "🗳️ Song of the Year tiebreaker"
        view = post.kwargs["view"]
        assert isinstance(view, SecretPollView)
        assert [b.item.custom_id for b in view.children] == [f"secret_poll:{poll.poll_id}:0",
                                                             f"secret_poll:{poll.poll_id}:1"]
        admin_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        [reply] = admin_interaction.sent
        assert reply.content.startswith(f"✅ Secret poll #{poll.poll_id} posted. It closes <t:")
        assert "I'll DM you the results then. Nobody else sees them." in reply.content

    async def test_the_length_can_be_chosen(self, admin_interaction):
        await secret_poll.callback(admin_interaction, "Quick one", "A | B", 2)

        assert get_recent_secret_polls()[0].closes_at == NOON + timedelta(hours=2)

    @pytest.mark.parametrize("options, message_start", [
        ("Only one", "❌ A poll needs at least 2 options"),
        (" | ", "❌ A poll needs at least 2 options"),
        (" | ".join(f"Option {i}" for i in range(MAX_OPTIONS + 1)), "❌ A poll can have at most 25 options"),
        (f"A | {'x' * (MAX_OPTION_LENGTH + 1)}", "❌ A button shows at most 80 characters"),
        ("IVE | ive", "❌ The same option appears more than once."),
    ])
    async def test_options_a_poll_cannot_show_are_refused(self, admin_interaction, options, message_start):
        await secret_poll.callback(admin_interaction, "Tiebreaker", options)

        [reply] = admin_interaction.sent
        assert reply.content.startswith(message_start) and reply.ephemeral
        assert admin_interaction.channel.sent == []
        assert get_recent_secret_polls() == []

    async def test_the_most_options_a_message_holds_is_fine(self, admin_interaction):
        await secret_poll.callback(admin_interaction, "Big", " | ".join(f"Option {i}" for i in range(MAX_OPTIONS)))

        assert len(admin_interaction.channel.sent[0].kwargs["view"].children) == 25

    async def test_if_the_post_fails_no_poll_is_left_behind(self, admin_interaction):
        admin_interaction.channel.send.side_effect = discord.Forbidden(
            mock.Mock(status=403, reason="Forbidden"), "Missing Permissions")

        with pytest.raises(discord.Forbidden):
            await secret_poll.callback(admin_interaction, "Tiebreaker", "A | B")

        assert get_recent_secret_polls() == []

    def test_the_options_have_limits_discord_enforces(self):
        params = {p.name: p for p in secret_poll.parameters}

        assert (params["title"].min_value, params["title"].max_value) == (1, 200)
        assert (params["hours"].min_value, params["hours"].max_value, params["hours"].default) == (1, 168, 24)


class TestSecretPollResults:
    """/secret-poll-results shows the count to the admin only."""

    async def test_shows_the_results_privately_while_open(self, admin_interaction):
        poll_id = create_secret_poll("Tiebreaker", ["A", "B"], 1, 10, NOON + timedelta(hours=24))
        record_secret_vote(poll_id, 5, 1, NOON)

        await secret_poll_results.callback(admin_interaction, poll_id)

        [reply] = admin_interaction.sent
        assert reply.ephemeral
        assert reply.content.startswith(f"🗳️ **Tiebreaker** (secret poll #{poll_id}, closes <t:")
        assert reply.content.endswith("1 vote\n• B: 1\n• A: 0\n🏆 Leading: B")

    async def test_a_closed_poll_shows_the_winner(self, admin_interaction):
        poll_id = create_secret_poll("Tiebreaker", ["A", "B"], 1, 10, NOON + timedelta(hours=24))
        record_secret_vote(poll_id, 5, 0, NOON)
        mark_secret_poll_closed(poll_id)

        await secret_poll_results.callback(admin_interaction, poll_id)

        assert get_secret_poll(poll_id).closed
        assert admin_interaction.sent[0].content.endswith("🏆 Winner: A")

    async def test_an_unknown_poll(self, admin_interaction):
        await secret_poll_results.callback(admin_interaction, 42)

        assert admin_interaction.sent[0].content == "❌ There is no secret poll #42."


class TestPollAutocomplete:
    """The results command suggests recent polls as the admin types."""

    async def test_matches_the_title_or_number_newest_first_with_status(self, admin_interaction):
        first = create_secret_poll("Song of the Year tiebreaker", ["A", "B"], 1, 10, NOON)
        second = create_secret_poll("Hall of Fame tiebreaker", ["A", "B"], 1, 10, NOON)
        mark_secret_poll_closed(first)

        everything = await _poll_autocomplete(admin_interaction, "TIEBREAKER")
        by_number = await _poll_autocomplete(admin_interaction, str(second))

        assert [(c.name, c.value) for c in everything] == [
            (f"#{second} Hall of Fame tiebreaker (open)", second),
            (f"#{first} Song of the Year tiebreaker (closed)", first)]
        assert [c.value for c in by_number] == [second]

    async def test_a_long_title_is_cut_to_what_discord_shows(self, admin_interaction):
        create_secret_poll("x" * 200, ["A", "B"], 1, 10, NOON)

        [choice] = await _poll_autocomplete(admin_interaction, "")

        assert len(choice.name) == 100
