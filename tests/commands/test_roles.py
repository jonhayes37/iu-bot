"""Tests for commands/roles.py"""

from unittest import mock

import discord
import pytest

from commands.roles import _build_display_chunks, register_role, sync_roles
from config import Channel, Database
from db.roles import get_display_message_ids, get_role_id, register_new_role, replace_display_message_ids

NOT_FOUND = discord.NotFound(mock.Mock(status=404, reason="Not Found"), "Unknown Message")


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
        assert (reply.via, reply.ephemeral) == ("followup", True)
        assert reply.content == "✅ The `#roles` display is up to date."

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


class TestDisplayChunks:
    """The text of the #roles display, split to fit Discord's 2000 character limit."""

    def test_no_roles_no_messages(self):
        assert not _build_display_chunks()

    def test_lists_each_category_with_its_roles_and_aliases(self):
        register_new_role(1, "Girl Groups", "Music", ["gg"])
        register_new_role(2, "Trivia", "Events", [])

        assert _build_display_chunks() == [
            "**Events**\n- `Trivia` (aliases `trivia`)\n\n"
            "**Music**\n- `Girl Groups` (aliases `gg`, `girl groups`)"]

    def test_categories_and_roles_are_sorted_ignoring_case(self):
        register_new_role(1, "zebra fans", "beta", [])
        register_new_role(2, "Apple fans", "Alpha", [])
        register_new_role(3, "banana fans", "Alpha", [])

        text = _build_display_chunks()[0]

        assert text.index("**Alpha**") < text.index("**beta**")
        assert text.index("`Apple fans`") < text.index("`banana fans`")

    def test_a_long_list_is_split_into_messages_that_fit_and_lose_nothing(self):
        for i in range(60):
            register_new_role(i + 1, f"A fairly long role name number {i}", "Everything",
                              [f"alias-{i}-one", f"alias-{i}-two"])

        chunks = _build_display_chunks()

        assert len(chunks) > 1
        assert all(len(chunk) <= 2000 for chunk in chunks)
        joined = "\n".join(chunks)
        assert all(f"`A fairly long role name number {i}`" in joined for i in range(60))
        assert all(line.startswith(("- `", "**")) for chunk in chunks for line in chunk.splitlines() if line)


    def test_many_categories_are_split_between_messages_too(self):
        for i in range(120):
            register_new_role(i + 1, f"R{i}", f"Category number {i:03}", [])

        chunks = _build_display_chunks()

        assert len(chunks) > 1 and all(len(chunk) <= 2000 for chunk in chunks)
        joined = "\n".join(chunks)
        assert all(f"**Category number {i:03}**" in joined for i in range(120))


class TestSyncDisplay:
    """/sync-roles brings the #roles messages in line with the database."""

    @staticmethod
    def _setup(make_guild, make_interaction, existing_ids=()):
        guild = make_guild(channels=(Channel.ROLES,))
        channel = guild.text_channels[0]
        replace_display_message_ids(list(existing_ids))
        return guild, channel, make_interaction(administrator=True, guild=guild)

    @staticmethod
    def _many_roles(count=60):
        for i in range(count):
            register_new_role(i + 1, f"A fairly long role name number {i}", "Everything", [f"alias-{i}-one"])

    async def test_new_messages_are_posted_and_remembered(self, make_guild, make_interaction):
        _, channel, interaction = self._setup(make_guild, make_interaction)
        register_new_role(1, "Girl Groups", "Music", [])

        await sync_roles.callback(interaction)

        [posted] = channel.sent
        assert posted.content.startswith("**Music**")
        assert len(get_display_message_ids()) == 1

    async def test_existing_messages_are_edited_in_place(self, make_guild, make_interaction):
        _, channel, interaction = self._setup(make_guild, make_interaction, existing_ids=[4242])
        register_new_role(1, "Girl Groups", "Music", [])
        existing = mock.MagicMock(spec=discord.Message, id=4242, edit=mock.AsyncMock())
        channel.fetch_message = mock.AsyncMock(return_value=existing)

        await sync_roles.callback(interaction)

        existing.edit.assert_awaited_once()
        assert existing.edit.await_args.kwargs["content"].startswith("**Music**")
        assert channel.sent == []
        assert get_display_message_ids() == [4242]

    async def test_a_message_someone_deleted_is_replaced_by_a_new_one(self, make_guild, make_interaction):
        _, channel, interaction = self._setup(make_guild, make_interaction, existing_ids=[4242])
        register_new_role(1, "Girl Groups", "Music", [])
        channel.fetch_message = mock.AsyncMock(side_effect=NOT_FOUND)

        await sync_roles.callback(interaction)

        assert len(channel.sent) == 1
        assert 4242 not in get_display_message_ids() and len(get_display_message_ids()) == 1

    async def test_more_messages_are_added_when_the_list_has_grown(self, make_guild, make_interaction):
        _, channel, interaction = self._setup(make_guild, make_interaction, existing_ids=[4242])
        self._many_roles()
        existing = mock.MagicMock(spec=discord.Message, id=4242, edit=mock.AsyncMock())
        channel.fetch_message = mock.AsyncMock(return_value=existing)

        await sync_roles.callback(interaction)

        chunks = _build_display_chunks()
        assert len(chunks) > 1
        assert existing.edit.await_count == 1 and len(channel.sent) == len(chunks) - 1
        assert len(get_display_message_ids()) == len(chunks)

    async def test_leftover_messages_are_deleted_when_the_list_shrinks(self, make_guild, make_interaction):
        _, channel, interaction = self._setup(make_guild, make_interaction, existing_ids=[1, 2, 3])
        register_new_role(1, "Girl Groups", "Music", [])
        fetched = {}

        async def fetch(message_id):
            fetched[message_id] = mock.MagicMock(spec=discord.Message, id=message_id, edit=mock.AsyncMock(),
                                                 delete=mock.AsyncMock())
            return fetched[message_id]

        channel.fetch_message = mock.AsyncMock(side_effect=fetch)

        await sync_roles.callback(interaction)

        fetched[1].edit.assert_awaited_once()
        fetched[2].delete.assert_awaited_once()
        fetched[3].delete.assert_awaited_once()
        assert get_display_message_ids() == [1]

    async def test_a_leftover_that_is_already_gone_is_fine(self, make_guild, make_interaction):
        _, channel, interaction = self._setup(make_guild, make_interaction, existing_ids=[1, 2])
        register_new_role(1, "Girl Groups", "Music", [])
        first = mock.MagicMock(spec=discord.Message, id=1, edit=mock.AsyncMock())
        channel.fetch_message = mock.AsyncMock(side_effect=[first, NOT_FOUND])

        await sync_roles.callback(interaction)

        assert get_display_message_ids() == [1]
        assert interaction.sent[0].content == "✅ The `#roles` display is up to date."
