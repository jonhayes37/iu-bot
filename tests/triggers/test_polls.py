"""Tests for triggers/polls.py: votes on the tournament polls."""

import datetime
import logging
from unittest import mock

import discord
import pytest

from config import Channel, Database
from db.merch import get_user_balance
from db.tournaments import create_tournament, set_match_poll_data
from triggers.polls import handle_poll_vote, handle_poll_vote_remove
from testsupport import fakes

VOTER = 50


@pytest.fixture(autouse=True)
def _databases(databases):
    databases(Database.TOURNAMENTS, Database.MERCH)


@pytest.fixture(name="server")
def _server(make_guild, make_client):
    """A server with #tournaments and #dispatch-news, and the tournament's bracket (two round-one polls)."""
    guild = make_guild(channels=(Channel.TOURNAMENTS, Channel.DISPATCH_NEWS))
    client = make_client(guild=guild)
    client.get_channel.side_effect = lambda channel_id: next((c for c in guild.channels if c.id == channel_id), None)
    tournament_id = create_tournament("Best Ballad", "d", ["A", "B", "C", "D"], 2)
    polls = {}

    def payload(user_id=VOTER, message_id=None, answer_id=1, channel=None):
        raw = mock.MagicMock(spec=discord.RawPollVoteActionEvent)
        raw.user_id = user_id
        raw.message_id = message_id or polls["first"]
        raw.answer_id = answer_id
        raw.channel_id = (channel or guild.text_channels[0]).id
        raw.guild_id = guild.id
        return raw

    return mock.Mock(guild=guild, client=client, news=guild.text_channels[1], tournament_id=tournament_id,
                     polls=polls, payload=payload, tournaments=guild.text_channels[0])


@pytest.fixture(autouse=True)
def _polls_up(server, query):
    """Each round-one match has a poll: 1000 + match id."""
    matches = query(Database.TOURNAMENTS, "SELECT match_id FROM tournament_matches WHERE round_num = 1 "
                                          "ORDER BY match_position")
    for match in matches:
        set_match_poll_data(match["match_id"], 1000 + match["match_id"], datetime.datetime(2030, 1, 1))
    server.polls["first"], server.polls["second"] = (1000 + m["match_id"] for m in matches)


def _votes(query):
    return {(r["match_id"], r["user_id"]): r["choice_entrant_id"]
            for r in query(Database.TOURNAMENTS, "SELECT * FROM tournament_votes")}


class TestVoting:
    """A vote is saved, and completing a round earns a heart."""

    async def test_a_vote_is_recorded(self, server, query):
        await handle_poll_vote(server.client, server.payload())

        assert len(_votes(query)) == 1

    async def test_votes_on_polls_that_are_not_tournament_matches_are_ignored(self, server, query):
        await handle_poll_vote(server.client, server.payload(message_id=99999))

        assert _votes(query) == {}

    async def test_the_bots_own_votes_are_ignored(self, server, query):
        await handle_poll_vote(server.client, server.payload(user_id=server.client.user.id))

        assert _votes(query) == {}

    async def test_polls_in_other_channels_are_ignored(self, server, query, make_channel):
        other = make_channel("general")
        server.client.get_channel.side_effect = lambda channel_id: other

        await handle_poll_vote(server.client, server.payload(channel=other))

        assert _votes(query) == {}

    async def test_a_channel_that_is_not_cached_gets_the_benefit_of_the_doubt(self, server, query):
        server.client.get_channel.side_effect = lambda channel_id: None

        await handle_poll_vote(server.client, server.payload())

        assert len(_votes(query)) == 1

    async def test_the_tournaments_channel_is_accepted(self, server, query):
        server.client.get_channel.side_effect = lambda channel_id: server.tournaments

        await handle_poll_vote(server.client, server.payload())

        assert len(_votes(query)) == 1

    async def test_changing_a_vote_replaces_it(self, server, query):
        await handle_poll_vote(server.client, server.payload(answer_id=1))
        await handle_poll_vote(server.client, server.payload(answer_id=2))

        assert len(_votes(query)) == 1


class TestReward:
    """Voting in every matchup of a round earns a heart and an announcement."""

    async def test_no_reward_until_the_last_matchup(self, server):
        await handle_poll_vote(server.client, server.payload(message_id=server.polls["first"]))

        assert get_user_balance(VOTER) == 0 and server.news.sent == []

    async def test_the_last_vote_pays_one_heart_and_announces_it(self, server):
        server.guild.members = [fakes.make_member(user_id=VOTER, name="Voter")]
        await handle_poll_vote(server.client, server.payload(message_id=server.polls["first"]))

        await handle_poll_vote(server.client, server.payload(message_id=server.polls["second"]))

        assert get_user_balance(VOTER) == 1
        [announcement] = server.news.sent
        assert announcement.content == (f"{server.guild.members[0].mention} earned 1 heart for voting in every "
                                        "single matchup for round 1 of **Best Ballad**!")

    async def test_a_member_who_left_the_server_is_mentioned_by_id(self, server):
        await handle_poll_vote(server.client, server.payload(message_id=server.polls["first"]))

        await handle_poll_vote(server.client, server.payload(message_id=server.polls["second"]))

        assert server.news.sent[0].content.startswith(f"<@{VOTER}> earned 1 heart")

    async def test_the_reward_is_paid_only_once(self, server):
        for _ in range(2):
            await handle_poll_vote(server.client, server.payload(message_id=server.polls["first"]))
            await handle_poll_vote(server.client, server.payload(message_id=server.polls["second"]))

        assert get_user_balance(VOTER) == 1 and len(server.news.sent) == 1

    async def test_without_a_dispatch_news_channel_the_reward_is_still_paid(self, server):
        server.guild.text_channels = [server.tournaments]
        await handle_poll_vote(server.client, server.payload(message_id=server.polls["first"]))

        await handle_poll_vote(server.client, server.payload(message_id=server.polls["second"]))

        assert get_user_balance(VOTER) == 1

    async def test_an_unknown_guild_means_no_announcement_but_the_reward_is_paid(self, server):
        server.client.get_guild.side_effect = lambda _: None
        await handle_poll_vote(server.client, server.payload(message_id=server.polls["first"]))

        await handle_poll_vote(server.client, server.payload(message_id=server.polls["second"]))

        assert get_user_balance(VOTER) == 1 and server.news.sent == []

    async def test_a_failure_to_announce_is_logged_not_raised(self, server, caplog):
        server.news.send.side_effect = discord.HTTPException(mock.Mock(status=500, reason="x"), "boom")
        await handle_poll_vote(server.client, server.payload(message_id=server.polls["first"]))

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await handle_poll_vote(server.client, server.payload(message_id=server.polls["second"]))

        assert "Could not announce the voting reward" in caplog.text
        assert get_user_balance(VOTER) == 1


class TestRemovingAVote:
    """Taking a vote back removes it."""

    async def test_a_retracted_vote_is_forgotten(self, server, query):
        await handle_poll_vote(server.client, server.payload(answer_id=1))

        await handle_poll_vote_remove(server.client, server.payload(answer_id=1))

        assert _votes(query) == {}

    async def test_retracting_the_old_answer_after_changing_keeps_the_new_vote(self, server, query):
        await handle_poll_vote(server.client, server.payload(answer_id=2))

        await handle_poll_vote_remove(server.client, server.payload(answer_id=1))

        assert len(_votes(query)) == 1

    async def test_the_bots_own_removals_are_ignored(self, server, query):
        await handle_poll_vote(server.client, server.payload(user_id=VOTER))

        await handle_poll_vote_remove(server.client, server.payload(user_id=server.client.user.id))

        assert len(_votes(query)) == 1

    async def test_polls_in_other_channels_are_ignored(self, server, query, make_channel):
        await handle_poll_vote(server.client, server.payload())
        other = make_channel("general")
        server.client.get_channel.side_effect = lambda channel_id: other

        await handle_poll_vote_remove(server.client, server.payload(channel=other))

        assert len(_votes(query)) == 1
