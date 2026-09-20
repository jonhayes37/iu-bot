"""Tests for bot.py: how the bot starts up and routes Discord events to the rest of the code."""

import logging
import sqlite3
from unittest import mock

import discord
import pytest
from discord import app_commands

import bot as bot_module
from bot import IUBot, on_app_command_error
from commands.registry import all_commands
from config import Channel, Database
from db.bot import save_bot_status_db
from ui.base import DATABASE_ERROR
from ui.eoy_nominations import HallOfFameNominationButton, Top25Button
from ui.eoy_voting import HallOfFameVoteButton, HMAVoteButton
from ui.hma_suggestions import HMASuggestButton
from ui.listen_game import JoinGameView
from ui.lists import SubmitListButton
from testsupport import fakes


@pytest.fixture(name="bot")
async def _bot():
    """An IU bot that has not connected to anything. `bot.user` is a fake member, the bot itself."""
    instance = IUBot()
    me = fakes.make_member(user_id=1, name="IU", bot=True)
    me.mentioned_in = mock.MagicMock(return_value=False)
    with mock.patch.object(IUBot, "user", new_callable=mock.PropertyMock, return_value=me):
        yield instance
    await instance.close()


class TestCreation:
    """Creating the bot has no side effects, and sets it up completely."""

    async def test_it_asks_discord_for_what_the_features_need(self, bot):
        assert bot.intents.message_content and bot.intents.members and bot.intents.reactions
        assert bot.intents.guilds and bot.intents.messages and bot.intents.polls

    async def test_every_command_in_the_commands_package_is_registered(self, bot):
        assert {c.name for c in bot.tree.get_commands()} == {c.name for c in all_commands()}
        assert len(bot.tree.get_commands()) == 46

    async def test_command_errors_are_reported_by_the_shared_handler(self, bot):
        assert bot.tree.on_error is on_app_command_error


class TestCommandErrors:
    """What a member sees when a command fails."""

    async def test_a_missing_role_names_the_role(self, interaction):
        await on_app_command_error(interaction, app_commands.MissingRole("Listen Game GM"))

        [reply] = interaction.sent
        assert (reply.content, reply.ephemeral) == ("❌ You must have the 'Listen Game GM' role to use this command.",
                                                    True)

    async def test_a_missing_permission_says_admins_only(self, interaction):
        await on_app_command_error(interaction, app_commands.MissingPermissions(["administrator"]))

        assert (interaction.sent[0].content, interaction.sent[0].ephemeral) == (
            "❌ Only server administrators can use this command.", True)

    async def test_anything_else_goes_to_the_shared_reporter(self, interaction):
        wrapped = app_commands.CommandInvokeError(mock.Mock(), sqlite3.OperationalError("locked"))

        await on_app_command_error(interaction, wrapped)

        assert interaction.sent[0].content == DATABASE_ERROR

    async def test_an_expired_interaction_does_not_raise(self, interaction, caplog):
        interaction.response.send_message.side_effect = discord.NotFound(mock.Mock(status=404, reason="x"), "Unknown")

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await on_app_command_error(interaction, ValueError("bug"))

        assert "Could not tell the user about an error" in caplog.text


class TestStartup:
    """setup_hook runs once per process and prepares buttons and commands."""

    @pytest.fixture(name="started")
    def _started(self, bot):
        """The bot with the parts of startup that talk to Discord replaced by mocks."""
        bot.add_dynamic_items = mock.Mock()
        bot.add_view = mock.Mock()
        bot.tree.sync = mock.AsyncMock()
        bot.tree.copy_global_to = mock.Mock()
        return bot

    async def test_the_buttons_are_registered_before_the_commands_are_synced(self, started):
        order = []
        started.add_dynamic_items.side_effect = lambda *_: order.append("buttons")
        started.tree.sync.side_effect = lambda **_: order.append("sync")

        await started.setup_hook()

        assert order == ["buttons", "sync"]

    async def test_every_button_that_carries_state_is_registered_as_a_dynamic_item(self, started):
        await started.setup_hook()

        assert set(started.add_dynamic_items.call_args.args) == {
            SubmitListButton, Top25Button, HallOfFameNominationButton, HallOfFameVoteButton, HMAVoteButton,
            HMASuggestButton}

    async def test_the_join_button_survives_a_restart(self, started):
        await started.setup_hook()

        [view] = started.add_view.call_args.args
        assert isinstance(view, JoinGameView)

    async def test_with_a_server_configured_commands_sync_to_it(self, started, monkeypatch):
        monkeypatch.setenv("DISCORD_GUILD", "12345")

        await started.setup_hook()

        started.tree.copy_global_to.assert_called_once_with(guild=discord.Object(id=12345))
        started.tree.sync.assert_awaited_once_with(guild=discord.Object(id=12345))

    async def test_without_a_server_commands_sync_globally(self, started, caplog):
        with caplog.at_level(logging.INFO, logger="iu-bot"):
            await started.setup_hook()

        started.tree.sync.assert_awaited_once_with()
        started.tree.copy_global_to.assert_not_called()
        assert "Global sync triggered" in caplog.text

    async def test_a_failed_sync_is_logged_and_does_not_stop_the_bot_starting(self, started, monkeypatch, caplog):
        monkeypatch.setenv("DISCORD_GUILD", "12345")
        started.tree.sync.side_effect = discord.HTTPException(mock.Mock(status=429, reason="Too Many Requests"),
                                                              "rate limited")

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await started.setup_hook()

        assert "Failed to sync commands" in caplog.text


class TestOnReady:
    """Once connected the background tasks start and the saved status is shown."""

    @pytest.fixture(name="ready")
    def _ready(self, bot, monkeypatch, databases, frozen_time):
        databases(Database.BOT)
        frozen_time("2026-03-17 12:00:00")
        monkeypatch.setenv("DISCORD_GUILD", "12345")
        bot.change_presence = mock.AsyncMock()
        loops = {}
        for name in ("check_upcoming_events", "tournament_resolution_loop", "check_listen_game_reminders"):
            loop = getattr(bot_module, name)
            monkeypatch.setattr(loop, "start", mock.Mock())
            monkeypatch.setattr(loop, "is_running", mock.Mock(return_value=False))
            loops[name] = loop
        bot.loops = loops
        monkeypatch.setattr(bot_module.write_heartbeat, "start", mock.Mock())
        monkeypatch.setattr(bot_module.write_heartbeat, "is_running", mock.Mock(return_value=False))
        return bot

    async def test_without_a_server_configured_nothing_starts(self, ready, monkeypatch):
        monkeypatch.delenv("DISCORD_GUILD")

        await ready.on_ready()

        assert not any(loop.start.called for loop in ready.loops.values())
        ready.change_presence.assert_not_awaited()

    async def test_the_heartbeat_starts_even_without_a_server_configured(self, ready, monkeypatch):
        monkeypatch.delenv("DISCORD_GUILD")

        await ready.on_ready()

        bot_module.write_heartbeat.start.assert_called_once_with(ready)

    async def test_a_reconnect_does_not_restart_the_heartbeat(self, ready):
        bot_module.write_heartbeat.is_running.return_value = True

        await ready.on_ready()

        bot_module.write_heartbeat.start.assert_not_called()

    async def test_the_three_background_tasks_start_for_the_server(self, ready):
        await ready.on_ready()

        for loop in ready.loops.values():
            loop.start.assert_called_once_with(ready, 12345)

    async def test_a_reconnect_does_not_start_a_task_that_is_already_running(self, ready):
        ready.loops["tournament_resolution_loop"].is_running.return_value = True

        await ready.on_ready()

        ready.loops["tournament_resolution_loop"].start.assert_not_called()
        ready.loops["check_upcoming_events"].start.assert_called_once()

    async def test_with_no_saved_status_the_presence_is_plain_online(self, ready):
        await ready.on_ready()

        ready.change_presence.assert_awaited_once_with(status=discord.Status.online, activity=None)

    async def test_a_saved_status_is_shown_as_listening(self, ready, execute):
        save_bot_status_db("Good Day", 7)
        execute(Database.BOT, "UPDATE statuses SET created_at = '2026-03-17 11:00:00'")

        await ready.on_ready()

        kwargs = ready.change_presence.await_args.kwargs
        assert kwargs["status"] is discord.Status.online
        assert (kwargs["activity"].type, kwargs["activity"].name) == (discord.ActivityType.listening, "Good Day")

    async def test_an_expired_status_is_not_shown(self, ready, execute):
        save_bot_status_db("Old news", 1)
        execute(Database.BOT, "UPDATE statuses SET created_at = '2026-03-10 11:00:00'")

        await ready.on_ready()

        assert ready.change_presence.await_args.kwargs["activity"] is None


class TestOnMessage:
    """Every message is routed to the features that care about its channel."""

    @pytest.fixture(name="routed", autouse=True)
    def _handlers(self, bot, monkeypatch):
        handlers = mock.Mock()
        for name in ("respond_to_ping", "store_new_release", "handle_role_assignment", "check_message_for_replies"):
            setattr(handlers, name, mock.AsyncMock())
            monkeypatch.setattr(bot_module, name, getattr(handlers, name))
        bot.handlers = handlers
        return handlers

    async def test_the_bots_own_messages_are_ignored(self, bot, make_message, make_guild):
        message = make_message("hi", author=bot.user, guild=make_guild())

        await bot.on_message(message)

        assert not any(getattr(bot.handlers, n).called for n in
                       ("respond_to_ping", "store_new_release", "handle_role_assignment", "check_message_for_replies"))

    async def test_an_ordinary_message_gets_keyword_replies(self, bot, make_message, make_guild):
        message = make_message("hi", channel="general", guild=make_guild())

        await bot.on_message(message)

        bot.handlers.check_message_for_replies.assert_awaited_once_with(message)
        bot.handlers.respond_to_ping.assert_not_awaited()

    async def test_a_direct_message_gets_keyword_replies(self, bot, make_message):
        message = make_message("hi", guild=None)

        await bot.on_message(message)

        bot.handlers.check_message_for_replies.assert_awaited_once_with(message)

    async def test_a_mention_from_a_person_gets_the_ping_reply_as_well(self, bot, make_message, make_guild):
        bot.user.mentioned_in.return_value = True
        message = make_message("hey @IU", guild=make_guild())

        await bot.on_message(message)

        bot.handlers.respond_to_ping.assert_awaited_once_with(message)
        bot.handlers.check_message_for_replies.assert_awaited_once_with(message)

    async def test_another_bot_never_gets_a_reply(self, bot, make_message, make_member, make_guild):
        bot.user.mentioned_in.return_value = True
        message = make_message("hey @IU 2am", author=make_member(user_id=99, bot=True), guild=make_guild())

        await bot.on_message(message)

        bot.handlers.respond_to_ping.assert_not_awaited()
        bot.handlers.check_message_for_replies.assert_not_awaited()

    async def test_links_in_new_releases_are_stored_and_the_message_still_gets_replies(
            self, bot, make_message, make_guild):
        message = make_message("https://youtu.be/dQw4w9WgXcQ", channel=Channel.NEW_RELEASES, guild=make_guild())

        await bot.on_message(message)

        bot.handlers.store_new_release.assert_awaited_once_with(message)
        bot.handlers.check_message_for_replies.assert_awaited_once_with(message)

    async def test_the_roles_channel_is_for_role_requests_only(self, bot, make_message, make_guild):
        message = make_message("add gg", channel=Channel.ROLES, guild=make_guild())

        await bot.on_message(message)

        bot.handlers.handle_role_assignment.assert_awaited_once_with(message)
        bot.handlers.check_message_for_replies.assert_not_awaited()

    async def test_the_dispatch_news_channel_never_gets_replies(self, bot, make_message, make_guild):
        message = make_message("2am", channel=Channel.DISPATCH_NEWS, guild=make_guild())

        await bot.on_message(message)

        bot.handlers.check_message_for_replies.assert_not_awaited()
        bot.handlers.store_new_release.assert_not_awaited()

    async def test_a_ping_in_the_roles_channel_is_still_answered_but_nothing_else(self, bot, make_message,
                                                                                 make_guild):
        bot.user.mentioned_in.return_value = True
        message = make_message("@IU add gg", channel=Channel.ROLES, guild=make_guild())

        await bot.on_message(message)

        bot.handlers.respond_to_ping.assert_awaited_once_with(message)
        bot.handlers.check_message_for_replies.assert_not_awaited()


class TestEventRouting:
    """Each Discord event reaches the right handler."""

    async def test_a_new_member_gets_the_role_then_the_welcome(self, bot, monkeypatch, make_member):
        order = []
        monkeypatch.setattr(bot_module, "add_trainee_role", mock.AsyncMock(side_effect=lambda m: order.append("role")))
        monkeypatch.setattr(bot_module, "welcome_member", mock.AsyncMock(side_effect=lambda m: order.append("welcome")))

        await bot.on_member_join(make_member())

        assert order == ["role", "welcome"]

    async def test_a_new_event_is_processed_as_new(self, bot, monkeypatch):
        process = mock.AsyncMock()
        monkeypatch.setattr(bot_module, "process_event", process)
        event = mock.Mock()

        await bot.on_scheduled_event_create(event)

        process.assert_awaited_once_with(event, is_update=False)

    async def test_an_updated_event_is_processed_using_its_new_state(self, bot, monkeypatch):
        process = mock.AsyncMock()
        monkeypatch.setattr(bot_module, "process_event", process)
        before, after = mock.Mock(), mock.Mock()

        await bot.on_scheduled_event_update(before, after)

        process.assert_awaited_once_with(after, is_update=True)

    async def test_poll_votes_go_to_the_poll_handlers(self, bot, monkeypatch):
        added, removed = mock.AsyncMock(), mock.AsyncMock()
        monkeypatch.setattr(bot_module, "handle_poll_vote", added)
        monkeypatch.setattr(bot_module, "handle_poll_vote_remove", removed)
        payload = mock.Mock()

        await bot.on_raw_poll_vote_add(payload)
        await bot.on_raw_poll_vote_remove(payload)

        added.assert_awaited_once_with(bot, payload)
        removed.assert_awaited_once_with(bot, payload)

    async def test_reactions_go_to_the_reaction_handler(self, bot, monkeypatch):
        handler = mock.AsyncMock()
        monkeypatch.setattr(bot_module, "handle_reaction_add", handler)
        payload = mock.Mock()

        await bot.on_raw_reaction_add(payload)

        handler.assert_awaited_once_with(payload, bot)
