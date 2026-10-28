"""Tests for ui/secret_poll.py: the poll post, its buttons, and the results text only the admin sees."""

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from config import Database
from db.bot import SecretPoll, create_secret_poll, get_secret_poll_counts, mark_secret_poll_closed
from ui.base import DATABASE_ERROR
from ui.secret_poll import CLOSED_TEXT, SecretPollView, SecretVoteButton, poll_embed, results_text
from testsupport.ui import button_labels, match_custom_id

NOON = datetime(2026, 12, 12, 12, 0, 0, tzinfo=timezone.utc)
CLOSES = NOON + timedelta(hours=24)


@pytest.fixture(autouse=True)
def _bot_database(databases, frozen_time):
    databases(Database.BOT)
    frozen_time("2026-12-12 12:00:00")


def _poll(closed=False, title="Tiebreaker"):
    return SecretPoll(7, title, 1, 10, 555, CLOSES, closed)


class TestPollEmbed:
    """The public post never shows a count."""

    def test_an_open_poll_says_how_to_vote_and_when_it_closes(self):
        embed = poll_embed("Song of the Year tiebreaker", CLOSES)

        assert embed.title == "🗳️ Song of the Year tiebreaker"
        assert "Your vote is secret" in embed.description
        assert f"<t:{int(CLOSES.timestamp())}:R>" in embed.description

    def test_a_closed_poll_only_says_voting_has_closed(self):
        assert poll_embed("Tiebreaker", CLOSES, closed=True).description == "Voting has closed."


class TestResultsText:
    """The results, sent only to the admin."""

    def test_votes_are_listed_most_first_with_the_winner(self):
        text = results_text(_poll(closed=True), [("A", 1), ("B", 3), ("C", 0)])

        assert text == ("🗳️ **Tiebreaker** (secret poll #7, closed)\n4 votes\n"
                        "• B: 3\n• A: 1\n• C: 0\n🏆 Winner: B")

    def test_an_open_poll_shows_the_leader_and_when_it_closes(self):
        text = results_text(_poll(), [("A", 1), ("B", 0)])

        assert f"closes <t:{int(CLOSES.timestamp())}:R>" in text
        assert text.endswith("1 vote\n• A: 1\n• B: 0\n🏆 Leading: A")

    def test_a_tie_for_the_most_votes_is_flagged_in_option_order(self):
        text = results_text(_poll(closed=True), [("A", 2), ("B", 1), ("C", 2)])

        assert text.endswith("• A: 2\n• C: 2\n• B: 1\n⚠️ Tied: A, C")

    def test_no_votes(self):
        assert results_text(_poll(closed=True), [("A", 0), ("B", 0)]).endswith("0 votes\nNobody has voted.")


class TestVoteButton:
    """Pressing an option records the vote and confirms it privately."""

    @pytest.fixture(name="poll_id")
    def _poll_id(self):
        return create_secret_poll("Tiebreaker", ["IVE - HEYA", "aespa - Supernova"], 1, 10, CLOSES)

    async def test_the_button_carries_the_poll_and_option(self, interaction):
        button = SecretVoteButton(3, 1, "aespa - Supernova")
        rebuilt = await SecretVoteButton.from_custom_id(
            interaction, mock.Mock(), match_custom_id(SecretVoteButton, "secret_poll:12:4"))

        assert (button.item.custom_id, button.item.label) == ("secret_poll:3:1", "aespa - Supernova")
        assert (rebuilt.poll_id, rebuilt.position) == (12, 4)
        assert match_custom_id(SecretVoteButton, "secret_poll:x:1") is None

    async def test_a_vote_is_recorded_and_confirmed_privately(self, interaction, poll_id):
        await SecretVoteButton(poll_id, 1).callback(interaction)

        assert get_secret_poll_counts(poll_id) == [("IVE - HEYA", 0), ("aespa - Supernova", 1)]
        [reply] = interaction.sent
        assert reply.ephemeral
        assert reply.content.startswith("🗳️ You voted for **aespa - Supernova**. Your vote is secret.")

    async def test_pressing_another_option_changes_the_vote(self, interaction, poll_id):
        await SecretVoteButton(poll_id, 1).callback(interaction)

        await SecretVoteButton(poll_id, 0).callback(interaction)

        assert get_secret_poll_counts(poll_id) == [("IVE - HEYA", 1), ("aespa - Supernova", 0)]

    async def test_a_closed_poll_refuses(self, interaction, poll_id):
        mark_secret_poll_closed(poll_id)

        await SecretVoteButton(poll_id, 0).callback(interaction)

        assert interaction.sent[0].content == f"🔒 {CLOSED_TEXT}"
        assert get_secret_poll_counts(poll_id)[0] == ("IVE - HEYA", 0)

    async def test_a_poll_past_its_time_refuses_before_the_closer_runs(self, interaction, poll_id, frozen_time):
        frozen_time("2026-12-13 12:00:00")

        await SecretVoteButton(poll_id, 0).callback(interaction)

        assert interaction.sent[0].content == f"🔒 {CLOSED_TEXT}"

    async def test_an_option_the_poll_does_not_have(self, interaction, poll_id):
        await SecretVoteButton(poll_id, 5).callback(interaction)

        assert interaction.sent[0].content == "❌ That option isn't part of this poll any more."

    async def test_a_database_failure_is_reported(self, interaction, poll_id, execute):
        execute(Database.BOT, "DROP TABLE secret_poll_votes")

        await SecretVoteButton(poll_id, 0).callback(interaction)

        assert interaction.sent[0].content == DATABASE_ERROR


async def test_the_view_has_a_button_per_option_and_never_times_out():
    view = SecretPollView(3, ["A", "B", "C"])

    assert view.timeout is None
    assert button_labels(view) == ["A", "B", "C"]
    assert [button.item.custom_id for button in view.children] == ["secret_poll:3:0", "secret_poll:3:1",
                                                                   "secret_poll:3:2"]
    assert not any(button.item.disabled for button in view.children)


async def test_a_closed_view_greys_out_every_button():
    assert all(button.item.disabled for button in SecretPollView(3, ["A", "B"], closed=True).children)
