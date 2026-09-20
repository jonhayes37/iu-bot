"""Fixtures for the command tests."""

from types import SimpleNamespace
from unittest import mock

import discord
import pytest

from config import Channel, Role
from testsupport import fakes

PLAYER_IDS = (1, 2, 101, 102, 103)          # 1 is the GM and 2 the substitute GM; 101-103 are the players


@pytest.fixture
def listen_server(make_guild, make_client, make_member):
    """
    A server set up for the Listen Game: a #listen-game channel, the Listen Game Player role, and
    members 1 (GM), 2 (substitute GM) and 101-103, who can all be DMed through the bot's client.

    `server.interaction(user_id)` is an interaction from that member in #listen-game, `server.dms(user_id)`
    the text of the DMs they were sent, and `server.blocked(user_id)` closes their DMs.
    """
    guild = make_guild(channels=(Channel.LISTEN_GAME,), roles=(Role.LISTEN_GAME_PLAYER,))
    members = {uid: make_member(user_id=uid, name=f"Member {uid}") for uid in PLAYER_IDS}
    guild.members = list(members.values())
    client = make_client(guild=guild)
    client.get_user.side_effect = members.get
    channel = guild.text_channels[0]

    def interaction(user_id=1):
        made = fakes.make_interaction(user=members[user_id], channel=channel, guild=guild)
        made.client = client
        return made

    def dms(user_id):
        return [message.content for message in members[user_id].sent]

    def blocked(user_id):
        members[user_id].send.side_effect = discord.Forbidden(mock.Mock(status=403, reason="x"), "closed")

    return SimpleNamespace(guild=guild, channel=channel, members=members, client=client, interaction=interaction,
                           dms=dms, blocked=blocked)
