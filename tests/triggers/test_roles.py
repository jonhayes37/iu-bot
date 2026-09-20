"""Tests for triggers/roles.py: members typing `add ...` / `remove ...` in #roles."""

import logging
import sqlite3
from unittest import mock

import discord
import pytest

from config import DEFAULT_ADMIN_USER_ID, Channel, Database
from db.roles import register_new_role
from triggers.roles import _get_intent_from_message, handle_role_assignment

FORBIDDEN = discord.Forbidden(mock.Mock(status=403, reason="Forbidden"), "Missing Permissions")


@pytest.fixture(autouse=True)
def _roles_database(databases):
    databases(Database.ROLES)


@pytest.fixture(name="typed")
def _typed(make_guild, make_member, make_message):
    """Builds a message a member types in #roles, in a server that has the role `Girl Groups` (alias `gg`)."""
    guild = make_guild(channels=(Channel.ROLES,), roles=("Girl Groups",))
    role = guild.roles[0]
    guild.get_role = mock.MagicMock(side_effect=lambda role_id: role if role_id == role.id else None)
    register_new_role(role.id, "Girl Groups", "Music", ["gg"])

    def build(text, has_role=False):
        member = make_member(user_id=50, name="Jo")
        member.roles = [role] if has_role else []
        message = make_message(text, author=member, channel=guild.text_channels[0], guild=guild)
        message.role = role
        return message

    return build


def _said(message):
    return [(m.content, m.kwargs.get("delete_after")) for m in message.channel.sent]


class TestIntent:
    """Reading what the member asked for."""

    @pytest.mark.parametrize("text, expected", [
        ("add gg", ("add", "gg")),
        ("add girl groups", ("add", "girl groups")),
        ("+gg", ("add", "gg")),
        ("+ gg", ("add", "gg")),
        ("remove gg", ("remove", "gg")),
        ("-gg", ("remove", "gg")),
        ("- gg", ("remove", "gg")),
        ("add   gg  ", ("add", "gg")),
    ])
    def test_valid_requests(self, text, expected):
        assert _get_intent_from_message(text) == expected

    @pytest.mark.parametrize("text", ["", "gg", "addgg", "removegg", "give gg", "hello there", "a add gg", "adding gg"])
    def test_anything_else_is_not_a_request(self, text):
        assert _get_intent_from_message(text) == ("", "")


class TestHandleRoleAssignment:
    """Every message in #roles is removed and answered briefly."""

    async def test_the_members_message_is_always_deleted_to_keep_the_channel_clean(self, typed):
        message = typed("add gg")

        await handle_role_assignment(message)

        message.delete.assert_awaited_once()

    async def test_missing_permission_to_delete_is_logged_and_the_request_still_works(self, typed, caplog):
        message = typed("add gg")
        message.delete.side_effect = FORBIDDEN

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await handle_role_assignment(message)

        assert "Failed to delete message in #roles" in caplog.text
        message.author.add_roles.assert_awaited_once_with(message.role)

    @pytest.mark.parametrize("text", ["add gg", "ADD GG", "+gg", "add Girl Groups", "  add gg  "])
    async def test_adding_a_role_by_alias_or_name_in_any_case(self, typed, text):
        message = typed(text)

        await handle_role_assignment(message)

        message.author.add_roles.assert_awaited_once_with(message.role)
        assert _said(message) == [("Granted the **Girl Groups** role!", 5.0)]

    async def test_adding_a_role_the_member_already_has(self, typed):
        message = typed("add gg", has_role=True)

        await handle_role_assignment(message)

        message.author.add_roles.assert_not_awaited()
        assert _said(message) == [("You already have the **Girl Groups** role!", 5.0)]

    @pytest.mark.parametrize("text", ["remove gg", "-gg", "REMOVE Girl Groups"])
    async def test_removing_a_role(self, typed, text):
        message = typed(text, has_role=True)

        await handle_role_assignment(message)

        message.author.remove_roles.assert_awaited_once_with(message.role)
        assert _said(message) == [("Removed the **Girl Groups** role!", 5.0)]

    async def test_removing_a_role_the_member_does_not_have(self, typed):
        message = typed("remove gg")

        await handle_role_assignment(message)

        message.author.remove_roles.assert_not_awaited()
        assert _said(message) == [("You don't have the **Girl Groups** role!", 5.0)]

    @pytest.mark.parametrize("text", ["hello", "gg", "grant gg", ""])
    async def test_a_message_that_is_not_a_request_gets_a_hint(self, typed, text):
        message = typed(text)

        await handle_role_assignment(message)

        assert _said(message) == [("Invalid prefix! Must be either `add`, `+`, `remove`, or `-`.", 5.0)]
        message.author.add_roles.assert_not_awaited()

    async def test_an_unknown_role_is_named_back_to_the_member(self, typed):
        message = typed("add boy groups")

        await handle_role_assignment(message)

        assert _said(message) == [("Could not find a role matching `boy groups`.", 5.0)]

    async def test_a_role_that_is_in_the_database_but_not_in_discord_pings_the_admin(self, typed):
        message = typed("add gg")
        message.guild.get_role.side_effect = lambda _: None

        await handle_role_assignment(message)

        assert _said(message) == [
            (f"Role exists in database but not in Discord! Ping <@{DEFAULT_ADMIN_USER_ID}>.", 5.0)]

    async def test_a_database_failure_is_logged_and_the_member_told_to_try_again(self, typed, monkeypatch, caplog):
        message = typed("add gg")
        monkeypatch.setattr("triggers.roles.get_role_id", mock.Mock(side_effect=sqlite3.OperationalError("locked")))

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await handle_role_assignment(message)

        assert "Could not look up the role for 'gg'" in caplog.text
        assert _said(message) == [
            ("Something went wrong looking up that role. Please try again in a moment.", 5.0)]

    @pytest.mark.parametrize("text, has_role", [("add gg", False), ("remove gg", True)])
    async def test_a_bot_without_permission_says_so(self, typed, text, has_role):
        message = typed(text, has_role=has_role)
        message.author.add_roles.side_effect = FORBIDDEN
        message.author.remove_roles.side_effect = FORBIDDEN

        await handle_role_assignment(message)

        assert _said(message) == [("I don't have permission to add that role!", 6.0)]
