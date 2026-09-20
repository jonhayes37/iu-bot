"""Tests for commands/tournaments.py"""

import io
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from commands.tournaments import (
    MAX_DAYS_PER_ROUND, MAX_ENTRANT_NAME_LENGTH, force_close_round, new_tournament
)
from config import Channel, Database
from db.tournaments import create_tournament, get_expired_unresolved_matches
from testsupport import fakes

NOW = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
FOUR = "Song 1 | Song 2 | Song 3 | Song 4"


@pytest.fixture(autouse=True)
def _databases(databases, frozen_time):
    databases(Database.TOURNAMENTS)
    frozen_time("2026-03-17 12:00:00")


@pytest.fixture(name="admin")
def _admin(make_guild):
    """An admin in a server with #tournaments, whose channel can post polls."""
    guild = make_guild(channels=("general", Channel.TOURNAMENTS))
    channel = guild.text_channels[1]

    async def send(content=None, **kwargs):
        channel.sent.append(fakes.Sent("channel", content, kwargs))
        if "poll" in kwargs:
            return fakes.make_poll_message(fakes.next_id(), expires_at=NOW + kwargs["poll"].duration)
        return fakes.make_message()

    channel.send = mock.AsyncMock(side_effect=send)
    return fakes.make_interaction(guild=guild, channel=guild.text_channels[0], administrator=True)


@pytest.fixture(name="bracket", autouse=True)
def _bracket(monkeypatch):
    render = mock.AsyncMock(side_effect=lambda _: io.BytesIO(b"PNG"))
    monkeypatch.setattr("commands.tournaments.generate_bracket_image", render)
    return render


def _polls(admin):
    return [m.kwargs["poll"] for m in admin.guild.text_channels[1].sent if "poll" in m.kwargs]


class TestNewTournamentValidation:
    """Everything is checked before anything is created."""

    async def test_it_defers_first_because_creating_the_bracket_takes_a_while(self, admin):
        await new_tournament.callback(admin, "T", "d", FOUR)

        admin.response.defer.assert_awaited_once_with(ephemeral=True)

    @pytest.mark.parametrize("entrants", ["", "A", "A | B", "A | B | C", "  |  | "])
    async def test_fewer_than_four_tracks_is_refused(self, admin, entrants):
        await new_tournament.callback(admin, "T", "d", entrants)

        assert admin.sent[0].content == "You need at least 4 tracks to run a bracket!"

    @pytest.mark.parametrize("count", [5, 6, 7, 9, 12, 20])
    async def test_a_number_that_is_not_a_power_of_two_is_refused(self, admin, count):
        entrants = " | ".join(f"Song {i}" for i in range(count))

        await new_tournament.callback(admin, "T", "d", entrants)

        assert admin.sent[0].content == \
            f"Tournaments require a power of two (4, 8, 16, 32), but you provided **{count}**."

    @pytest.mark.parametrize("count", [4, 8, 16, 32])
    async def test_powers_of_two_are_accepted(self, admin, count):
        entrants = " | ".join(f"Song {i}" for i in range(count))

        await new_tournament.callback(admin, "T", "d", entrants)

        assert admin.sent[0].content.startswith("Successfully created tournament")

    @pytest.mark.parametrize("days", [0, -1, MAX_DAYS_PER_ROUND + 1])
    async def test_a_round_length_outside_discords_poll_limit_is_refused(self, admin, days):
        await new_tournament.callback(admin, "T", "d", FOUR, days)

        assert admin.sent[0].content.startswith("Each round must last between 1 and 32 days")
        assert f"**{days}**" in admin.sent[0].content

    @pytest.mark.parametrize("days", [1, 2, MAX_DAYS_PER_ROUND])
    async def test_round_lengths_within_the_limit_are_accepted(self, admin, days):
        await new_tournament.callback(admin, "T", "d", FOUR, days)

        assert admin.sent[0].content.startswith("Successfully created tournament")

    async def test_track_names_too_long_for_a_poll_answer_are_listed(self, admin):
        long_name = "x" * (MAX_ENTRANT_NAME_LENGTH + 1)

        await new_tournament.callback(admin, "T", "d", f"{long_name} | B | C | D")

        content = admin.sent[0].content
        assert content.startswith("Discord polls only allow 55 characters per entrant. Please shorten these:")
        assert f"• {long_name} (56 characters)" in content

    async def test_a_name_of_exactly_the_limit_is_fine(self, admin):
        await new_tournament.callback(admin, "T", "d", f"{'x' * MAX_ENTRANT_NAME_LENGTH} | B | C | D")

        assert admin.sent[0].content.startswith("Successfully created tournament")

    async def test_at_most_five_long_names_are_shown(self, admin):
        names = " | ".join(f"{'y' * 60}{i}" for i in range(8))

        await new_tournament.callback(admin, "T", "d", names)

        assert admin.sent[0].content.count("• ") == 5

    async def test_a_server_without_the_tournaments_channel_creates_nothing(self, make_guild, make_interaction, query):
        interaction = make_interaction(guild=make_guild(channels=("general",)), administrator=True)

        await new_tournament.callback(interaction, "T", "d", FOUR)

        assert interaction.sent[0].content == "I can't find the #tournaments channel, so nothing was created."
        assert query(Database.TOURNAMENTS, "SELECT * FROM tournaments") == []

    async def test_a_refused_tournament_creates_nothing(self, admin, query):
        await new_tournament.callback(admin, "T", "d", "A | B | C")

        assert query(Database.TOURNAMENTS, "SELECT * FROM tournaments") == []
        assert admin.guild.text_channels[1].sent == []


class TestNewTournament:
    """Creating and launching a tournament."""

    async def test_creates_the_tournament_with_its_entrants_in_seed_order(self, admin, query):
        await new_tournament.callback(admin, "Best Ballad", "Pick the best", FOUR, 3)

        tournament = query(Database.TOURNAMENTS, "SELECT * FROM tournaments")[0]
        assert (tournament["name"], tournament["description"], tournament["days_per_round"]) == \
            ("Best Ballad", "Pick the best", 3)
        entrants = query(Database.TOURNAMENTS, "SELECT name, seed FROM tournament_entrants ORDER BY seed")
        assert [(e["name"], e["seed"]) for e in entrants] == [(f"Song {i}", i) for i in range(1, 5)]

    async def test_the_days_per_round_default_to_two(self, admin, query):
        await new_tournament.callback(admin, "T", "d", FOUR)

        assert query(Database.TOURNAMENTS, "SELECT days_per_round FROM tournaments")[0][0] == 2

    async def test_posts_the_announcement_with_the_bracket_picture(self, admin):
        await new_tournament.callback(admin, "Best Ballad", "Pick the best", FOUR)

        announcement = admin.guild.text_channels[1].sent[0]
        assert announcement.content == ("🏆 **Best Ballad has begun!** 🏆\nPick the best\n\n"
                                        "Round 1 voting polls will appear below shortly!")
        assert announcement.kwargs["file"].filename.startswith("bracket_")
        assert announcement.kwargs["file"].filename.endswith(".png")

    async def test_the_announcement_admits_when_the_picture_could_not_be_made(self, admin, bracket):
        bracket.side_effect = None
        bracket.return_value = None

        await new_tournament.callback(admin, "Best Ballad", "d", FOUR)

        announcement = admin.guild.text_channels[1].sent[0]
        assert announcement.content.endswith("\n\n*(The bracket image couldn't be generated this time.)*")
        assert announcement.kwargs["file"] is None

    async def test_launches_the_round_one_polls(self, admin):
        await new_tournament.callback(admin, "T", "d", FOUR, 4)

        polls = _polls(admin)
        assert [p.question for p in polls] == ["Round 1 | Song 1 vs Song 4", "Round 1 | Song 2 vs Song 3"]
        assert all(p.duration == timedelta(days=4) for p in polls)

    async def test_confirms_to_the_admin_with_the_id_and_channel(self, admin, query):
        await new_tournament.callback(admin, "T", "d", FOUR)

        tournament_id = query(Database.TOURNAMENTS, "SELECT tournament_id FROM tournaments")[0][0]
        assert admin.sent[0].content == (f"Successfully created tournament `{tournament_id}`, posted the bracket, and "
                                         f"launched Round 1 polls in {admin.guild.text_channels[1].mention}!")

    async def test_names_are_trimmed_and_empty_slots_ignored(self, admin, query):
        await new_tournament.callback(admin, "T", "d", " Song 1 |Song 2|| Song 3 | Song 4 |")

        names = query(Database.TOURNAMENTS, "SELECT name FROM tournament_entrants ORDER BY seed")
        assert [n[0] for n in names] == ["Song 1", "Song 2", "Song 3", "Song 4"]


class TestForceCloseRound:
    """/force-close-round makes live polls due now."""

    async def test_live_polls_are_made_due_and_the_admin_is_told_how_many(self, admin, query):
        await new_tournament.callback(admin, "T", "d", FOUR)
        tournament_id = query(Database.TOURNAMENTS, "SELECT tournament_id FROM tournaments")[0][0]
        admin.sent.clear()
        assert get_expired_unresolved_matches() == []

        await force_close_round.callback(admin, tournament_id)

        [reply] = admin.sent
        assert reply.content.startswith("⏩ **Fast-forwarded 2 matches!**")
        assert "within 5 minutes" in reply.content
        assert len(get_expired_unresolved_matches()) == 2

    async def test_a_tournament_with_no_live_polls(self, admin):
        tournament_id = create_tournament("T", "d", ["A", "B", "C", "D"], 2)      # created, but no polls posted yet

        await force_close_round.callback(admin, tournament_id)

        assert admin.sent[0].content == ("⚠️ **No active polls found.**\nThere are no unresolved polls currently "
                                         f"running for tournament `{tournament_id}`.")

    async def test_an_unknown_tournament(self, admin):
        await force_close_round.callback(admin, "unknown-id")

        assert admin.sent[0].content.startswith("⚠️ **No active polls found.**")

    async def test_the_reply_is_private(self, admin):
        await force_close_round.callback(admin, "x")

        admin.response.defer.assert_awaited_once_with(ephemeral=True)
