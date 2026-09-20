"""Tests for commands/roles.py"""

from unittest import mock

import discord
import pytest

from commands.roles import register_role, sync_roles
from config import Channel, Database
from db.roles import get_role_id, register_new_role


@pytest.fixture(autouse=True)
def _roles_database(databases):
    databases(Database.ROLES)


def _discord_role(role_id=200, name="Rookies"):
    role = mock.MagicMock(spec=discord.Role)
    role.id = role_id
    role.name = name
    return role


async def test_a_clashing_alias_is_refused_with_a_clear_message_and_nothing_changes(make_interaction, make_guild):
    register_new_role(100, "Girl Groups", "Music", ["gg"])
    interaction = make_interaction(administrator=True, guild=make_guild(channels=(Channel.ROLES,)))

    await register_role.callback(interaction, _discord_role(), "Music", "gg, fresh")

    [reply] = interaction.sent
    assert reply.ephemeral
    assert reply.content.startswith("❌ Couldn't register **Rookies**, so nothing was changed.")
    assert "`gg` is already used by **Girl Groups**" in reply.content
    assert "fresh" not in reply.content
    assert get_role_id("gg") == 100
    assert get_role_id("fresh") is None
    assert get_role_id("rookies") is None
    interaction.guild.text_channels[0].send.assert_not_called()


async def test_every_clash_is_listed(make_interaction, make_guild):
    register_new_role(100, "Girl Groups", "Music", ["gg", "girls"])
    interaction = make_interaction(administrator=True, guild=make_guild(channels=(Channel.ROLES,)))

    await register_role.callback(interaction, _discord_role(), "Music", "gg, girls")

    [reply] = interaction.sent
    assert "`gg` is already used by **Girl Groups**" in reply.content
    assert "`girls` is already used by **Girl Groups**" in reply.content


async def test_without_a_clash_the_role_is_registered_and_the_list_refreshed(make_interaction, make_guild):
    interaction = make_interaction(administrator=True, guild=make_guild(channels=(Channel.ROLES,)))

    await register_role.callback(interaction, _discord_role(), "Music", "fresh")

    assert get_role_id("fresh") == 200
    assert interaction.sent[-1].content == "Registered **Rookies** under **Music** and updated the channel!"
    assert interaction.guild.text_channels[0].sent   # the #roles display was posted


async def test_without_a_roles_channel_the_role_is_still_registered(make_interaction, make_guild):
    interaction = make_interaction(administrator=True, guild=make_guild(channels=()))

    await register_role.callback(interaction, _discord_role(), "Music", "")

    assert get_role_id("rookies") == 200
    assert "couldn't find the `#roles` channel" in interaction.sent[-1].content


class TestSyncRoles:
    """/sync-roles refreshes the #roles display and says it has."""

    async def test_it_is_acknowledged_first_then_confirmed_privately(self, make_interaction, make_guild):
        register_new_role(100, "Girl Groups", "Music", ["gg"])
        interaction = make_interaction(administrator=True, guild=make_guild(channels=(Channel.ROLES,)))

        await sync_roles.callback(interaction)

        interaction.response.defer.assert_awaited_once()
        [reply] = interaction.sent
        assert (reply.via, reply.content, reply.ephemeral) == ("followup", "✅ The `#roles` display is up to date.", True)

    async def test_the_roles_are_posted_to_the_channel(self, make_interaction, make_guild):
        register_new_role(100, "Girl Groups", "Music", ["gg"])
        guild = make_guild(channels=(Channel.ROLES,))
        interaction = make_interaction(administrator=True, guild=guild)

        await sync_roles.callback(interaction)

        [posted] = guild.text_channels[0].sent
        assert posted.content == "**Music**\n- `Girl Groups` (aliases `gg`, `girl groups`)"

    async def test_a_missing_roles_channel_is_reported_instead_of_silence(self, make_interaction, make_guild):
        interaction = make_interaction(administrator=True, guild=make_guild(channels=()))

        await sync_roles.callback(interaction)

        [reply] = interaction.sent
        assert (reply.content, reply.ephemeral) == ("❌ I couldn't find the `#roles` channel.", True)
