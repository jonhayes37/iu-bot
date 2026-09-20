"""Tests for triggers/merch.py: hearts given by reacting, and the 5-reaction milestone."""

import collections
from unittest import mock

import discord
import pytest

from config import Channel, Database
from db.merch import get_user_balance, is_milestone_paid
from triggers.merch import _paid_milestones, _reaction_totals, _remember, handle_reaction_add
from testsupport import fakes

SENDER, AUTHOR, MESSAGE_ID = 10, 20, 5000


@pytest.fixture(autouse=True)
def _merch_database(databases, frozen_time):
    databases(Database.MERCH)
    frozen_time("2026-03-17 15:00:00")


@pytest.fixture(autouse=True)
def _forget_what_was_learned():
    """The module remembers messages between events; every test starts with a clean memory."""
    _reaction_totals.clear()
    _paid_milestones.clear()
    yield
    _reaction_totals.clear()
    _paid_milestones.clear()


def _reaction(*users, count=None):
    """A reaction on a message, made by the given users."""
    async def generate():
        for user in users:
            yield user

    return mock.Mock(count=len(users) if count is None else count, users=generate)


@pytest.fixture(name="server")
def _server(make_guild, make_client, make_member):
    """A server with #dispatch-news, a message by AUTHOR (id 5000), and the bot's client."""
    guild = make_guild(channels=("general", Channel.DISPATCH_NEWS))
    client = make_client(guild=guild)
    general, news = guild.text_channels
    message = fakes.make_message("great song", author=make_member(user_id=AUTHOR, name="Author"), channel=general)
    message.id = MESSAGE_ID
    message.reactions = []
    general.fetch_message = mock.AsyncMock(return_value=message)
    client.get_channel.side_effect = lambda channel_id: general if channel_id == general.id else None

    def payload(emoji="giveHeart", user_id=SENDER, author_id=AUTHOR, member=None, guild_id=guild.id):
        raw = mock.MagicMock(spec=discord.RawReactionActionEvent)
        raw.guild_id = guild_id
        raw.channel_id = general.id
        raw.message_id = MESSAGE_ID
        raw.user_id = user_id
        raw.member = member
        raw.message_author_id = author_id
        raw.emoji = mock.Mock()
        raw.emoji.name = emoji
        return raw

    def humans(count, first_id=100):
        return [make_member(user_id=first_id + i, name=f"Fan {i}") for i in range(count)]

    return mock.Mock(guild=guild, client=client, channel=general, news=news, message=message, payload=payload,
                     humans=humans, url=f"https://discord.com/channels/{guild.id}/{general.id}/{MESSAGE_ID}")


class TestIgnoredReactions:
    """Reactions that can never earn anything."""

    async def test_reactions_outside_a_server_are_ignored(self, server):
        await handle_reaction_add(server.payload(guild_id=None), server.client)

        assert get_user_balance(AUTHOR) == 0 and server.news.sent == []

    async def test_a_bots_reactions_are_ignored(self, server, make_member):
        await handle_reaction_add(server.payload(member=make_member(user_id=SENDER, bot=True)), server.client)

        assert get_user_balance(AUTHOR) == 0

    async def test_an_unknown_server_is_ignored(self, server):
        server.client.get_guild.side_effect = lambda _: None

        await handle_reaction_add(server.payload(), server.client)

        assert get_user_balance(AUTHOR) == 0


class TestDailyHeart:
    """Reacting with a heart emoji gives the message's author one of the sender's daily hearts."""

    @pytest.mark.parametrize("emoji", ["giveHeart", "aGiveHeart"])
    async def test_both_heart_emoji_give_a_heart_and_it_is_announced(self, server, emoji):
        await handle_reaction_add(server.payload(emoji=emoji), server.client)

        assert get_user_balance(AUTHOR) == 1
        [announcement] = server.news.sent
        assert announcement.content == f"<@{SENDER}> gave <@{AUTHOR}> their daily heart on {server.url}!"

    @pytest.mark.parametrize("emoji", ["👍", "heart", "giveheart", "wave"])
    async def test_other_emoji_give_nothing(self, server, emoji):
        await handle_reaction_add(server.payload(emoji=emoji), server.client)

        assert get_user_balance(AUTHOR) == 0 and server.news.sent == []

    async def test_a_member_cannot_heart_their_own_message(self, server):
        await handle_reaction_add(server.payload(user_id=AUTHOR), server.client)

        assert get_user_balance(AUTHOR) == 0 and server.news.sent == []

    async def test_only_one_heart_per_day_and_the_second_is_not_announced(self, server):
        await handle_reaction_add(server.payload(), server.client)
        await handle_reaction_add(server.payload(author_id=30), server.client)

        assert get_user_balance(AUTHOR) == 1 and get_user_balance(30) == 0
        assert len(server.news.sent) == 1

    async def test_the_next_day_the_member_can_give_another(self, server, frozen_time):
        await handle_reaction_add(server.payload(), server.client)
        frozen_time("2026-03-18 15:00:00")

        await handle_reaction_add(server.payload(), server.client)

        assert get_user_balance(AUTHOR) == 2

    async def test_the_reward_works_without_a_dispatch_news_channel(self, server):
        server.guild.text_channels = [server.channel]

        await handle_reaction_add(server.payload(), server.client)

        assert get_user_balance(AUTHOR) == 1

    async def test_the_author_comes_from_the_cached_message_when_the_event_lacks_it(self, server):
        server.client.cached_messages = [server.message]

        await handle_reaction_add(server.payload(author_id=None), server.client)

        assert get_user_balance(AUTHOR) == 1
        server.channel.fetch_message.assert_not_awaited()

    async def test_the_message_is_fetched_when_neither_the_event_nor_the_cache_knows_the_author(self, server):
        await handle_reaction_add(server.payload(author_id=None), server.client)

        assert get_user_balance(AUTHOR) == 1
        server.channel.fetch_message.assert_awaited()

    async def test_a_message_that_no_longer_exists_gives_nothing(self, server):
        server.channel.fetch_message.side_effect = discord.NotFound(mock.Mock(status=404, reason="x"), "gone")

        await handle_reaction_add(server.payload(author_id=None), server.client)

        assert get_user_balance(AUTHOR) == 0

    async def test_a_channel_the_bot_cannot_see_gives_nothing(self, server):
        server.client.get_channel.side_effect = lambda _: None

        await handle_reaction_add(server.payload(author_id=None), server.client)

        assert get_user_balance(AUTHOR) == 0


class TestMilestone:
    """A message reacted to by 5 different people earns its author 3 hearts, once."""

    def _cache_with_reactions(self, server, *reaction_groups):
        server.message.reactions = [_reaction(*users) for users in reaction_groups]
        server.client.cached_messages = [server.message]

    async def test_five_different_people_pay_the_author_three_hearts_and_it_is_announced(self, server):
        self._cache_with_reactions(server, server.humans(3, 100), server.humans(2, 200))

        await handle_reaction_add(server.payload(emoji="👍", user_id=100), server.client)

        assert get_user_balance(AUTHOR) == 3
        [announcement] = server.news.sent
        assert announcement.content == (f"<@{AUTHOR}>'s [post]({server.url}) "
                                        "got reactions from 5 people, and earned 3 hearts!")

    async def test_it_is_only_paid_once_however_many_more_reactions_come(self, server):
        self._cache_with_reactions(server, server.humans(6))

        for _ in range(3):
            await handle_reaction_add(server.payload(emoji="👍", user_id=100), server.client)

        assert get_user_balance(AUTHOR) == 3 and len(server.news.sent) == 1

    async def test_it_is_not_paid_again_after_a_restart_because_the_database_remembers(self, server):
        self._cache_with_reactions(server, server.humans(5))
        await handle_reaction_add(server.payload(emoji="👍", user_id=100), server.client)
        _paid_milestones.clear()

        await handle_reaction_add(server.payload(emoji="👍", user_id=100), server.client)

        assert get_user_balance(AUTHOR) == 3 and is_milestone_paid(MESSAGE_ID)

    async def test_fewer_than_five_reactions_pay_nothing(self, server):
        self._cache_with_reactions(server, server.humans(4))

        await handle_reaction_add(server.payload(emoji="👍", user_id=100), server.client)

        assert get_user_balance(AUTHOR) == 0

    async def test_the_same_people_reacting_with_several_emoji_count_once(self, server):
        fans = server.humans(3)
        self._cache_with_reactions(server, fans, fans)          # 6 reactions, but only 3 people

        await handle_reaction_add(server.payload(emoji="👍", user_id=100), server.client)

        assert get_user_balance(AUTHOR) == 0

    async def test_bots_do_not_count_towards_the_five(self, server, make_member):
        robots = [make_member(user_id=900 + i, bot=True) for i in range(2)]
        self._cache_with_reactions(server, server.humans(3) + robots)

        await handle_reaction_add(server.payload(emoji="👍", user_id=100), server.client)

        assert get_user_balance(AUTHOR) == 0

    async def test_a_milestone_works_without_a_dispatch_news_channel(self, server):
        server.guild.text_channels = [server.channel]
        self._cache_with_reactions(server, server.humans(5))

        await handle_reaction_add(server.payload(emoji="👍", user_id=100), server.client)

        assert get_user_balance(AUTHOR) == 3

    async def test_a_heart_reaction_can_complete_the_milestone_too(self, server):
        self._cache_with_reactions(server, server.humans(5))

        await handle_reaction_add(server.payload(emoji="giveHeart", user_id=SENDER), server.client)

        assert get_user_balance(AUTHOR) == 1 + 3          # the daily heart and the milestone


class TestMessagesNotInTheCache:
    """An old message is fetched once to learn its count, then the count is tracked without more fetches."""

    async def test_the_message_is_fetched_once_and_later_reactions_are_counted_from_memory(self, server):
        server.message.reactions = [_reaction(*server.humans(3))]           # 3 reactions when first seen

        await handle_reaction_add(server.payload(emoji="👍"), server.client)
        await handle_reaction_add(server.payload(emoji="👍"), server.client)        # 4 (no fetch)

        assert server.channel.fetch_message.await_count == 1
        assert get_user_balance(AUTHOR) == 0

    async def test_reaching_five_fetches_the_message_again_to_verify_and_pay(self, server):
        server.message.reactions = [_reaction(*server.humans(3))]
        await handle_reaction_add(server.payload(emoji="👍"), server.client)
        await handle_reaction_add(server.payload(emoji="👍"), server.client)
        server.message.reactions = [_reaction(*server.humans(5))]           # now really 5 people

        await handle_reaction_add(server.payload(emoji="👍"), server.client)

        assert server.channel.fetch_message.await_count == 2
        assert get_user_balance(AUTHOR) == 3

    async def test_a_message_deleted_before_the_final_check_pays_nothing(self, server):
        server.message.reactions = [_reaction(*server.humans(4))]
        await handle_reaction_add(server.payload(emoji="👍"), server.client)      # learns 4, remembers it
        server.channel.fetch_message.side_effect = discord.NotFound(mock.Mock(status=404, reason="x"), "gone")

        await handle_reaction_add(server.payload(emoji="👍"), server.client)      # the 5th, but it can't be verified

        assert get_user_balance(AUTHOR) == 0

    async def test_a_message_that_has_gone_stops_processing(self, server):
        server.channel.fetch_message.side_effect = discord.NotFound(mock.Mock(status=404, reason="x"), "gone")

        await handle_reaction_add(server.payload(emoji="👍"), server.client)

        assert get_user_balance(AUTHOR) == 0

    async def test_a_message_already_known_to_be_paid_costs_nothing(self, server):
        server.message.reactions = [_reaction(*server.humans(5))]
        await handle_reaction_add(server.payload(emoji="👍"), server.client)
        assert get_user_balance(AUTHOR) == 3
        server.channel.fetch_message.reset_mock()

        await handle_reaction_add(server.payload(emoji="👍"), server.client)

        server.channel.fetch_message.assert_not_awaited()


class TestRememberedMessages:
    """What is remembered about messages is bounded."""

    def test_the_oldest_entries_are_dropped_beyond_the_limit(self, monkeypatch):
        monkeypatch.setattr("triggers.merch._REMEMBERED_MESSAGES", 3)
        cache = collections.OrderedDict()

        for message_id in range(1, 6):
            _remember(cache, message_id, message_id * 10)

        assert list(cache) == [3, 4, 5]

    def test_updating_an_entry_keeps_it_fresh(self, monkeypatch):
        monkeypatch.setattr("triggers.merch._REMEMBERED_MESSAGES", 3)
        cache = collections.OrderedDict()
        for message_id in (1, 2, 3):
            _remember(cache, message_id, 0)

        _remember(cache, 1, 99)
        _remember(cache, 4, 0)

        assert list(cache) == [3, 1, 4] and cache[1] == 99
