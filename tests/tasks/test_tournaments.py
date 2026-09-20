"""Tests for tasks/tournaments.py: polls, resolving matches, moving between rounds, and the finale."""

import io
import logging
from datetime import datetime, timedelta, timezone
from unittest import mock

import discord
import pytest

from config import Channel, Database
from db.merch import get_award_recipient, get_user_balance
from db.tournaments import (
    advance_winner, create_tournament, get_active_tournament_id, get_expired_unresolved_matches, get_unpolled_matches,
    record_vote, set_match_poll_data
)
from tasks.tournaments import (
    _process_expired_matches, check_round_completion, post_round_polls, tournament_resolution_loop
)
from testsupport import fakes

NOW = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
NOT_FOUND = discord.NotFound(mock.Mock(status=404, reason="Not Found"), "Unknown Message")


@pytest.fixture(autouse=True)
def _databases(databases, frozen_time):
    databases(Database.TOURNAMENTS, Database.MERCH)
    frozen_time("2026-03-17 12:00:00")


@pytest.fixture(name="server")
def _server(make_guild, make_client):
    """The server with #tournaments and #dispatch-news, where the tournaments channel can post polls."""
    guild = make_guild(channels=(Channel.TOURNAMENTS, Channel.DISPATCH_NEWS))
    channel = guild.text_channels[0]

    async def send(content=None, **kwargs):
        channel.sent.append(fakes.Sent("channel", content, kwargs))
        if "poll" in kwargs:
            return fakes.make_poll_message(fakes.next_id(), expires_at=NOW + kwargs["poll"].duration)
        return fakes.make_message()

    channel.send = mock.AsyncMock(side_effect=send)
    return mock.Mock(guild=guild, channel=channel, news=guild.text_channels[1], client=make_client(guild=guild))


@pytest.fixture(name="bracket", autouse=True)
def _bracket(monkeypatch):
    """Bracket rendering, returning a small fake picture."""
    render = mock.AsyncMock(side_effect=lambda _: io.BytesIO(b"PNG"))
    monkeypatch.setattr("tasks.tournaments.generate_bracket_image", render)
    return render


@pytest.fixture(name="no_waiting")
def _no_waiting(monkeypatch):
    """Skips the pause the loop takes to let Discord catch up, recording how long it would have been."""
    waited = []

    async def wait(seconds):
        waited.append(seconds)

    monkeypatch.setattr("tasks.tournaments.asyncio.sleep", wait)
    return waited


def _make(entrants=4, name="Best Ballad", days=2):
    return create_tournament(name, "d", [f"Song {i}" for i in range(1, entrants + 1)], days)


def _matches(query, tournament_id, round_num):
    return query(Database.TOURNAMENTS,
                 "SELECT * FROM tournament_matches WHERE tournament_id = ? AND round_num = ? ORDER BY match_position",
                 tournament_id, round_num)


def _put_polls_up(query, tournament_id, round_num, *, ends=NOW - timedelta(hours=1)):
    """Gives each match in the round a poll message (id 1000 + match id) that ended at `ends`."""
    for match in _matches(query, tournament_id, round_num):
        set_match_poll_data(match["match_id"], 1000 + match["match_id"], ends)


def _resolve_round(query, tournament_id, round_num, winners="a"):
    """Marks every match in the round as won by its first (or second) entrant and moves them on."""
    for match in _matches(query, tournament_id, round_num):
        winner = match["entrant_a_id"] if winners == "a" else match["entrant_b_id"]
        advance_winner(match["match_id"], tournament_id, round_num, match["match_position"], winner)


def _serve_polls(server, messages):
    """Makes the channel return the given poll messages (by their id) when fetched."""
    by_id = {message.id: message for message in messages}

    async def fetch(message_id):
        if isinstance(by_id.get(message_id), Exception):
            raise by_id[message_id]
        return by_id[message_id]

    server.channel.fetch_message = mock.AsyncMock(side_effect=fetch)


def _voters():
    """The two members who voted in the finished tournament of TestFinale."""
    return [fakes.make_member(user_id=11, name="Eleven"), fakes.make_member(user_id=12, name="Twelve")]


def _sent_texts(channel):
    return [message.content for message in channel.sent]


class TestPostRoundPolls:
    """Each waiting match gets a Discord poll."""

    async def test_posts_a_two_answer_poll_for_each_match(self, server):
        tournament_id = _make(4)

        await post_round_polls(server.channel, tournament_id, 1, days_per_round=3)

        polls = [message.kwargs["poll"] for message in server.channel.sent]
        assert [poll.question for poll in polls] == ["Round 1 | Song 1 vs Song 4", "Round 1 | Song 2 vs Song 3"]
        assert [[a.text for a in poll.answers] for poll in polls] == [["Song 1", "Song 4"], ["Song 2", "Song 3"]]
        assert all(poll.duration == timedelta(days=3) and poll.multiple is False for poll in polls)

    async def test_the_poll_and_the_expiry_discord_set_are_remembered(self, server, query):
        tournament_id = _make(4)

        await post_round_polls(server.channel, tournament_id, 1, days_per_round=2)

        matches = _matches(query, tournament_id, 1)
        assert all(m["message_id"] for m in matches)
        assert all(m["end_timestamp"] == (NOW + timedelta(days=2)).isoformat() for m in matches)

    async def test_the_local_clock_is_used_if_discord_returns_no_poll(self, server, query):
        tournament_id = _make(4)

        async def send(**_):
            return mock.MagicMock(id=555, poll=None)

        server.channel.send = mock.AsyncMock(side_effect=send)

        await post_round_polls(server.channel, tournament_id, 1, days_per_round=2)

        assert _matches(query, tournament_id, 1)[0]["end_timestamp"] == (NOW + timedelta(days=2)).isoformat()

    async def test_a_poll_that_fails_to_post_does_not_stop_the_rest_and_can_be_retried(self, server, caplog):
        tournament_id = _make(4)
        real_send = server.channel.send.side_effect
        calls = []

        async def flaky(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise discord.HTTPException(mock.Mock(status=500, reason="x"), "boom")
            return await real_send(**kwargs)

        server.channel.send = mock.AsyncMock(side_effect=flaky)

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await post_round_polls(server.channel, tournament_id, 1, days_per_round=2)

        assert "Failed to post poll for match" in caplog.text
        assert len(calls) == 2
        assert len(get_unpolled_matches(tournament_id, 1)) == 1        # the first is still waiting

    async def test_a_round_with_nothing_to_post_says_so_and_posts_nothing(self, server, caplog):
        tournament_id = _make(4)

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await post_round_polls(server.channel, tournament_id, 2, days_per_round=2)    # round 2 has no entrants yet

        assert "No unpolled matches found" in caplog.text
        assert server.channel.sent == []


class TestProcessExpiredMatches:
    """When a poll ends, the entrant with more votes moves on."""

    @pytest.fixture(name="round_one")
    def _round_one(self, query):
        tournament_id = _make(4)
        _put_polls_up(query, tournament_id, 1)
        return tournament_id, get_expired_unresolved_matches()

    async def _resolve(self, server, expired, votes, *, finalised=True):
        """Serves a poll per expired match with the given (a, b) votes, and resolves them."""
        polls = [fakes.make_poll_message(m["message_id"], (f"A{i}", f"B{i}"), votes[i], finalised=finalised)
                 for i, m in enumerate(expired)]
        _serve_polls(server, polls)
        await _process_expired_matches(server.channel, expired)
        return polls

    @staticmethod
    def _winners(query, tournament_id):
        names = {r["entrant_id"]: r["name"] for r in query(Database.TOURNAMENTS, "SELECT * FROM tournament_entrants")}
        return [names.get(m["winner_id"]) for m in _matches(query, tournament_id, 1)]

    async def test_the_entrant_with_more_votes_wins(self, server, query, round_one):
        tournament_id, expired = round_one

        await self._resolve(server, expired, [(5, 2), (1, 9)])

        assert self._winners(query, tournament_id) == ["Song 1", "Song 3"]

    async def test_winners_are_placed_in_the_next_round(self, server, query, round_one):
        tournament_id, expired = round_one

        await self._resolve(server, expired, [(5, 2), (1, 9)])

        [final] = _matches(query, tournament_id, 2)
        names = {r["entrant_id"]: r["name"] for r in query(Database.TOURNAMENTS, "SELECT * FROM tournament_entrants")}
        assert (names[final["entrant_a_id"]], names[final["entrant_b_id"]]) == ("Song 1", "Song 3")

    async def test_a_tie_goes_to_the_higher_seed(self, server, query, round_one):
        tournament_id, expired = round_one

        await self._resolve(server, expired, [(3, 3), (0, 0)])

        # Song 1 (seed 1) beats Song 4; Song 2 (seed 2) beats Song 3
        assert self._winners(query, tournament_id) == ["Song 1", "Song 2"]

    async def test_a_tie_in_a_later_round_still_goes_to_the_higher_seed_even_in_the_second_slot(
            self, server, query, round_one):
        tournament_id, expired = round_one
        await self._resolve(server, expired, [(0, 1), (1, 0)])     # Song 4 (seed 4) and Song 2 (seed 2) advance
        [final] = _matches(query, tournament_id, 2)
        set_match_poll_data(final["match_id"], 2001, NOW - timedelta(hours=1))
        _serve_polls(server, [fakes.make_poll_message(2001, ("Song 4", "Song 2"), (3, 3))])

        await _process_expired_matches(server.channel, get_expired_unresolved_matches())

        names = {r["entrant_id"]: r["name"] for r in query(Database.TOURNAMENTS, "SELECT * FROM tournament_entrants")}
        assert names[_matches(query, tournament_id, 2)[0]["winner_id"]] == "Song 2"

    async def test_a_poll_still_open_is_closed_first_so_the_count_is_final(self, server, round_one):
        _, expired = round_one

        polls = await self._resolve(server, expired, [(5, 2), (1, 9)], finalised=False)

        assert all(poll.end_poll.await_count == 1 for poll in polls)

    async def test_a_poll_that_has_already_closed_is_not_closed_again(self, server, round_one):
        _, expired = round_one

        polls = await self._resolve(server, expired, [(5, 2), (1, 9)], finalised=True)

        assert all(poll.end_poll.await_count == 0 for poll in polls)

    async def test_if_discord_closed_it_meanwhile_its_final_state_is_read(self, server, query, round_one):
        tournament_id, expired = round_one
        first = fakes.make_poll_message(expired[0]["message_id"], ("A", "B"), (1, 4), finalised=False)
        first.end_poll.side_effect = discord.HTTPException(mock.Mock(status=400, reason="x"), "already closed")
        closed = fakes.make_poll_message(expired[0]["message_id"], ("A", "B"), (1, 4), finalised=True)
        second = fakes.make_poll_message(expired[1]["message_id"], ("C", "D"), (4, 1), finalised=True)
        server.channel.fetch_message = mock.AsyncMock(side_effect=[first, closed, second])

        await _process_expired_matches(server.channel, expired)

        assert self._winners(query, tournament_id) == ["Song 4", "Song 2"]

    async def test_a_poll_that_vanishes_when_it_is_closed_is_skipped(self, server, query, round_one, caplog):
        tournament_id, expired = round_one
        open_poll = fakes.make_poll_message(expired[0]["message_id"], ("A", "B"), (1, 4), finalised=False)
        open_poll.end_poll.side_effect = None
        open_poll.end_poll.return_value = mock.MagicMock(poll=None)
        second = fakes.make_poll_message(expired[1]["message_id"], ("C", "D"), (4, 1))
        _serve_polls(server, [open_poll, second])

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await _process_expired_matches(server.channel, expired)

        assert "is not a poll" in caplog.text
        assert self._winners(query, tournament_id) == [None, "Song 2"]

    async def test_a_message_that_is_not_a_poll_is_skipped_and_the_others_still_resolve(
            self, server, query, round_one, caplog):
        tournament_id, expired = round_one
        not_a_poll = fakes.make_message()
        not_a_poll.id = expired[0]["message_id"]
        not_a_poll.poll = None
        second = fakes.make_poll_message(expired[1]["message_id"], ("C", "D"), (4, 1))
        _serve_polls(server, [not_a_poll, second])

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await _process_expired_matches(server.channel, expired)

        assert "is not a poll" in caplog.text
        assert self._winners(query, tournament_id) == [None, "Song 2"]

    async def test_a_deleted_poll_is_reported_and_the_others_still_resolve(self, server, query, round_one, caplog):
        tournament_id, expired = round_one
        second = fakes.make_poll_message(expired[1]["message_id"], ("C", "D"), (4, 1))
        server.channel.fetch_message = mock.AsyncMock(side_effect=[NOT_FOUND, second])

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await _process_expired_matches(server.channel, expired)

        assert "was deleted by a user" in caplog.text
        assert self._winners(query, tournament_id) == [None, "Song 2"]

    async def test_an_unexpected_error_on_one_match_is_reported_and_the_others_still_resolve(
            self, server, query, round_one, caplog):
        tournament_id, expired = round_one
        second = fakes.make_poll_message(expired[1]["message_id"], ("C", "D"), (4, 1))
        server.channel.fetch_message = mock.AsyncMock(side_effect=[RuntimeError("boom"), second])

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await _process_expired_matches(server.channel, expired)

        assert f"Error resolving match {expired[0]['match_id']}: boom" in caplog.text
        assert self._winners(query, tournament_id) == [None, "Song 2"]


class TestRoundTransitions:
    """check_round_completion posts the next round when the last one is done."""

    async def test_a_round_still_in_progress_posts_nothing(self, server, bracket, query):
        tournament_id = _make(4)
        _put_polls_up(query, tournament_id, 1)

        await check_round_completion(server.channel, tournament_id, 2)

        assert server.channel.sent == []
        bracket.assert_not_awaited()

    async def test_the_first_round_is_announced_with_its_polls(self, server):
        tournament_id = _make(4)

        await check_round_completion(server.channel, tournament_id, 2)

        texts = _sent_texts(server.channel)
        assert texts[0] == "**Round 1 starts now!**"
        assert len([m for m in server.channel.sent if "poll" in m.kwargs]) == 2
        assert not any("complete" in (text or "") for text in texts)

    async def test_finishing_a_round_announces_it_with_the_bracket_and_starts_the_next(self, server, query):
        tournament_id = _make(4)
        _put_polls_up(query, tournament_id, 1)
        _resolve_round(query, tournament_id, 1)

        await check_round_completion(server.channel, tournament_id, 2)

        sent = server.channel.sent
        assert sent[0].content == "**Round 1 is now complete!**"
        assert sent[1].content == "Here is the updated tournament bracket:"
        assert sent[1].kwargs["file"].filename == "bracket_r1_complete.png"
        assert sent[2].content == "**Round 2 starts now!**"
        assert sent[3].kwargs["poll"].question == "Round 2 | Song 1 vs Song 2"

    async def test_no_bracket_picture_is_posted_when_rendering_fails(self, server, bracket, query):
        bracket.side_effect = None
        bracket.return_value = None
        tournament_id = _make(4)
        _put_polls_up(query, tournament_id, 1)
        _resolve_round(query, tournament_id, 1)

        await check_round_completion(server.channel, tournament_id, 2)

        assert not any("file" in message.kwargs for message in server.channel.sent)
        assert _sent_texts(server.channel)[:2] == ["**Round 1 is now complete!**", "**Round 2 starts now!**"]

    async def test_polls_that_failed_to_post_earlier_are_posted_without_a_new_announcement(
            self, server, bracket, query):
        tournament_id = _make(4)
        first, _ = _matches(query, tournament_id, 1)
        set_match_poll_data(first["match_id"], 1001, NOW + timedelta(days=1))    # only one poll made it up

        await check_round_completion(server.channel, tournament_id, 2)

        [message] = server.channel.sent                     # just the missing poll, no "Round 1 starts now!"
        assert message.kwargs["poll"].question == "Round 1 | Song 2 vs Song 3"
        bracket.assert_not_awaited()

    async def test_days_per_round_sets_how_long_the_polls_run(self, server):
        tournament_id = _make(4)

        await check_round_completion(server.channel, tournament_id, 5)

        assert server.channel.sent[1].kwargs["poll"].duration == timedelta(days=5)


class TestFinale:
    """When the last match is decided the champion and a raffle winner are announced."""

    @pytest.fixture(name="finished")
    def _finished(self, query):
        """A two-entrant tournament whose final has been won by Song 2, with votes cast by users 11 and 12."""
        tournament_id = _make(2, name="Best Ballad")
        [final] = _matches(query, tournament_id, 1)
        set_match_poll_data(final["match_id"], 7001, NOW - timedelta(hours=1))
        record_vote(7001, 11, 1)
        record_vote(7001, 12, 2)
        advance_winner(final["match_id"], tournament_id, 1, 1, final["entrant_b_id"])
        return tournament_id

    async def test_announces_the_champion_with_the_final_bracket(self, server, finished):
        await check_round_completion(server.channel, finished, 2)

        [announcement] = server.channel.sent
        assert announcement.content.startswith("The **Best Ballad** tournament has concluded, and the Grand Champion "
                                               "is **Song 2**!")
        assert announcement.kwargs["file"].filename == "bracket_final.png"

    async def test_the_tournament_is_then_marked_finished(self, server, finished):
        assert get_active_tournament_id() == finished

        await check_round_completion(server.channel, finished, 2)

        assert get_active_tournament_id() is None

    async def test_the_raffle_winner_gets_five_hearts_and_is_named(self, server, finished, query):
        server.guild.members = _voters()

        await check_round_completion(server.channel, finished, 2)

        recipient = get_award_recipient(f"[raffle:{finished}]")
        assert recipient in (11, 12) and get_user_balance(recipient) == 5
        transaction = query(Database.MERCH, "SELECT * FROM transactions")[0]
        assert transaction["reason"] == f"Won the raffle for Best Ballad! [raffle:{finished}]"
        text = server.channel.sent[0].content
        assert "**Participation Raffle**" in text
        assert "Total Pool: 2 votes" in text
        assert f"<@{recipient}>" in text and "You had 1 votes" in text

    async def test_the_win_is_also_announced_in_dispatch_news(self, server, finished):
        server.guild.members = _voters()

        await check_round_completion(server.channel, finished, 2)

        [news] = server.news.sent
        assert "earned **5 hearts** for winning the participation raffle for the **Best Ballad**!" in news.content

    async def test_a_retry_after_a_failure_pays_the_same_winner_only_once(self, server, finished, query):
        server.guild.members = _voters()
        real_send = server.channel.send.side_effect
        server_error = discord.HTTPException(mock.Mock(status=500, reason="x"), "boom")
        server.channel.send = mock.AsyncMock(side_effect=server_error)
        with pytest.raises(discord.HTTPException):
            await check_round_completion(server.channel, finished, 2)
        assert get_active_tournament_id() == finished          # not marked finished, so the next check retries
        first_winner = get_award_recipient(f"[raffle:{finished}]")
        server.channel.send = mock.AsyncMock(side_effect=real_send)
        server.news.sent.clear()

        await check_round_completion(server.channel, finished, 2)

        assert get_award_recipient(f"[raffle:{finished}]") == first_winner
        assert get_user_balance(first_winner) == 5
        assert len(query(Database.MERCH, "SELECT * FROM transactions")) == 1
        assert server.news.sent == []                          # not announced a second time
        assert f"<@{first_winner}>" in server.channel.sent[0].content
        assert get_active_tournament_id() is None

    async def test_a_winner_who_left_the_server_is_mentioned_by_id(self, server, finished, caplog):
        server.guild.fetch_member.side_effect = NOT_FOUND

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await check_round_completion(server.channel, finished, 2)

        recipient = get_award_recipient(f"[raffle:{finished}]")
        assert f"<@{recipient}>" in server.channel.sent[0].content
        assert "is no longer in the guild" in caplog.text
        assert get_active_tournament_id() is None

    async def test_without_a_dispatch_news_channel_the_finale_still_happens(self, server, finished):
        server.guild.text_channels = [server.channel]

        await check_round_completion(server.channel, finished, 2)

        assert len(server.channel.sent) == 1
        assert get_active_tournament_id() is None

    async def test_a_tournament_nobody_voted_in_has_no_raffle(self, server, query):
        tournament_id = _make(2, name="Quiet")
        [final] = _matches(query, tournament_id, 1)
        advance_winner(final["match_id"], tournament_id, 1, 1, final["entrant_a_id"])

        await check_round_completion(server.channel, tournament_id, 2)

        assert "Participation Raffle" not in server.channel.sent[0].content
        assert query(Database.MERCH, "SELECT * FROM transactions") == []
        assert get_active_tournament_id() is None

    async def test_the_finale_is_posted_without_a_picture_if_rendering_fails(self, server, bracket, finished):
        bracket.side_effect = None
        bracket.return_value = None

        await check_round_completion(server.channel, finished, 2)

        assert server.channel.sent[0].kwargs["file"] is None


class TestResolutionLoop:
    """Every five minutes the loop resolves finished polls and moves the tournament on."""

    async def _tick(self, server):
        await tournament_resolution_loop.coro(server.client, server.guild.id)

    async def test_runs_every_five_minutes(self):
        assert tournament_resolution_loop.minutes == 5

    async def test_an_unknown_guild_is_reported(self, make_client, caplog):
        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await tournament_resolution_loop.coro(make_client(), 999)

        assert "Could not find guild with ID: 999" in caplog.text

    async def test_a_server_without_the_tournaments_channel_is_reported(self, make_guild, make_client, caplog):
        guild = make_guild(channels=("general",))

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await tournament_resolution_loop.coro(make_client(guild=guild), guild.id)

        assert "Could not find #tournaments channel" in caplog.text

    async def test_with_no_tournament_running_nothing_happens(self, server):
        await self._tick(server)

        assert server.channel.sent == []

    async def test_ended_polls_are_resolved_and_the_next_round_starts_in_the_same_tick(
            self, server, no_waiting, query):
        tournament_id = _make(4)
        _put_polls_up(query, tournament_id, 1)
        matches = _matches(query, tournament_id, 1)
        _serve_polls(server, [fakes.make_poll_message(matches[0]["message_id"], ("A", "B"), (5, 1)),
                              fakes.make_poll_message(matches[1]["message_id"], ("C", "D"), (0, 3))])

        await self._tick(server)

        assert no_waiting == [10]
        assert _sent_texts(server.channel)[0] == "**Round 1 is now complete!**"
        assert "**Round 2 starts now!**" in _sent_texts(server.channel)
        [final] = _matches(query, tournament_id, 2)
        assert final["entrant_a_id"] and final["entrant_b_id"]

    async def test_the_pause_grows_with_the_number_of_matches_resolved(self, server, no_waiting, query):
        tournament_id = _make(16)
        _put_polls_up(query, tournament_id, 1)
        matches = _matches(query, tournament_id, 1)
        _serve_polls(server, [fakes.make_poll_message(m["message_id"], ("A", "B"), (2, 1)) for m in matches])

        await self._tick(server)

        assert no_waiting == [16]              # 8 matches, two seconds each

    async def test_with_no_polls_ending_the_active_tournament_is_checked_for_its_next_step(self, server, no_waiting):
        _make(4)

        await self._tick(server)

        assert no_waiting == []
        assert _sent_texts(server.channel)[0] == "**Round 1 starts now!**"

    async def test_an_error_is_logged_and_the_next_tick_still_runs(self, server, monkeypatch, caplog):
        monkeypatch.setattr("tasks.tournaments.get_expired_unresolved_matches", mock.Mock(side_effect=OSError("disk")))

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await self._tick(server)

        assert "Unhandled error in tournament resolution loop" in caplog.text
