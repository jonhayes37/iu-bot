"""Tests for services/listen_game.py"""

import logging
from unittest import mock

import discord
import pytest

from config import Database
from db.listen_game import (
    GameStatus, RoundStatus, close_round_db, get_current_round_db, set_round_theme_db, upsert_submission_db
)
from services.listen_game import (
    NO_ACTIVE_GAME, NO_ACTIVE_ROUND, RoundContext, playlist_link, require_active_round, send_dm,
    update_submission_tracker
)
from testsupport.listen_game import start_game


@pytest.fixture(autouse=True)
def _listen_game_database(databases):
    databases(Database.LISTEN_GAME)


def _forbidden():
    return discord.Forbidden(mock.Mock(status=403, reason="Forbidden"), "Cannot send messages to this user")


def _http_error():
    return discord.HTTPException(mock.Mock(status=500, reason="Server Error"), "boom")


class TestRequireActiveRound:
    """Commands start by loading the current game and round, or telling the user why they can't."""

    async def test_no_game_is_reported_and_returns_none(self, interaction):
        assert await require_active_round(interaction, deferred=False) is None

        [reply] = interaction.sent
        assert (reply.via, reply.content, reply.ephemeral) == ("response", NO_ACTIVE_GAME, True)

    async def test_a_game_that_is_only_registering_is_not_active(self, interaction, execute):
        start_game()
        execute(Database.LISTEN_GAME, "UPDATE listen_games SET status = 'registration'")

        assert await require_active_round(interaction, deferred=False) is None
        assert interaction.sent[0].content == NO_ACTIVE_GAME

    async def test_a_deferred_command_is_answered_with_a_followup(self, interaction):
        await require_active_round(interaction, deferred=True)

        [reply] = interaction.sent
        assert (reply.via, reply.content, reply.ephemeral) == ("followup", NO_ACTIVE_GAME, True)

    async def test_a_game_with_no_round_in_play(self, interaction, execute):
        start_game()
        execute(Database.LISTEN_GAME, "UPDATE listen_rounds SET status = 'completed'")

        assert await require_active_round(interaction, deferred=False) is None

        assert interaction.sent[0].content == NO_ACTIVE_ROUND

    async def test_returns_the_game_and_current_round(self, interaction):
        game_id = start_game()

        ctx = await require_active_round(interaction, deferred=False)

        assert isinstance(ctx, RoundContext)
        assert (ctx.game.game_id, ctx.game.status) == (game_id, GameStatus.PLAYING)
        assert (ctx.round.game_id, ctx.round.host_id, ctx.round.status) == (game_id, 101, RoundStatus.SETTING_THEME)
        assert interaction.sent == []

    async def test_any_status_is_fine_when_none_are_required(self, interaction):
        game_id = start_game()
        set_round_theme_db(get_current_round_db(game_id).round_id, "t")

        assert await require_active_round(interaction, deferred=False) is not None

    async def test_a_round_in_an_allowed_status_is_returned(self, interaction):
        game_id = start_game()
        set_round_theme_db(get_current_round_db(game_id).round_id, "t")

        ctx = await require_active_round(interaction, deferred=False, statuses=(RoundStatus.SUBMITTING,))

        assert ctx.round.status is RoundStatus.SUBMITTING

    async def test_a_round_in_the_wrong_status_gets_the_commands_own_message(self, interaction):
        start_game()

        ctx = await require_active_round(interaction, deferred=False, statuses=(RoundStatus.SUBMITTING,),
                                         wrong_status_message="Submissions aren't open yet.")

        assert ctx is None
        assert interaction.sent[0].content == "Submissions aren't open yet."
        assert interaction.sent[0].ephemeral

    async def test_a_default_message_is_used_when_the_command_gives_none(self, interaction):
        start_game()

        await require_active_round(interaction, deferred=False, statuses=(RoundStatus.RANKING,))

        assert interaction.sent[0].content == "⚠️ The round isn't in the right phase for that."

    async def test_several_allowed_statuses(self, interaction):
        game_id = start_game()
        current = get_current_round_db(game_id).round_id
        set_round_theme_db(current, "t")
        close_round_db(current)

        ctx = await require_active_round(interaction, deferred=False,
                                         statuses=(RoundStatus.SUBMITTING, RoundStatus.RANKING))

        assert ctx.round.status is RoundStatus.RANKING


class TestSendDm:
    """DMs can fail, and that must never crash a command."""

    async def test_sends_to_a_cached_user(self, make_client, make_member):
        client, user = make_client(), make_member(user_id=5)
        client.get_user.return_value = user

        assert await send_dm(client, 5, "hello") is True

        assert [m.content for m in user.sent] == ["hello"]
        client.fetch_user.assert_not_called()

    async def test_fetches_a_user_who_is_not_cached(self, make_client, make_member):
        client, user = make_client(), make_member(user_id=5)
        client.get_user.return_value = None
        client.fetch_user.return_value = user

        assert await send_dm(client, 5, "hello") is True

        client.fetch_user.assert_awaited_once_with(5)
        assert [m.content for m in user.sent] == ["hello"]

    async def test_closed_dms_return_false_and_are_logged(self, make_client, make_member, caplog):
        client, user = make_client(), make_member(user_id=5)
        client.get_user.return_value = user
        user.send.side_effect = _forbidden()

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            assert await send_dm(client, 5, "hello") is False

        assert "Could not DM user 5 (their DMs are closed)" in caplog.text

    async def test_a_user_who_no_longer_exists_returns_false(self, make_client, caplog):
        client = make_client()
        client.get_user.return_value = None
        client.fetch_user.side_effect = discord.NotFound(mock.Mock(status=404, reason="Not Found"), "Unknown User")

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            assert await send_dm(client, 5, "hello") is False

        assert "Could not DM user 5" in caplog.text

    async def test_a_discord_error_returns_false(self, make_client, make_member):
        client, user = make_client(), make_member(user_id=5)
        client.get_user.return_value = user
        user.send.side_effect = _http_error()

        assert await send_dm(client, 5, "hello") is False


class TestPlaylistLink:
    """The playlist link shown to players."""

    def test_links_to_the_playlist(self):
        assert playlist_link("PLabc") == "https://www.youtube.com/playlist?list=PLabc"

    @pytest.mark.parametrize("missing", [None, ""])
    def test_no_playlist(self, missing):
        assert playlist_link(missing) == "No playlist generated."


class TestUpdateSubmissionTracker:
    """The live 'x/y submissions' message under the ruleset."""

    @pytest.fixture
    def ctx_and_channel(self, make_channel):
        game_id = start_game()           # players 101, 102, 103; 101 is the host, so 2 songs are needed
        current = get_current_round_db(game_id)
        current.status_message_id = 9001
        ctx = RoundContext(game=mock.Mock(game_id=game_id), round=current)
        channel = make_channel("listen-game")
        tracker = mock.MagicMock(spec=discord.Message)
        tracker.edit = mock.AsyncMock()
        channel.fetch_message = mock.AsyncMock(return_value=tracker)
        return ctx, channel, tracker

    async def test_shows_submitted_out_of_needed(self, ctx_and_channel):
        ctx, channel, tracker = ctx_and_channel
        upsert_submission_db(ctx.round.round_id, 102, "v1", "t1")

        await update_submission_tracker(channel, ctx)

        channel.fetch_message.assert_awaited_once_with(9001)
        tracker.edit.assert_awaited_once_with(
            content="🎧 **Round Status:** We are at `1/2` submissions for the round.")

    async def test_extra_text_is_added_to_the_end(self, ctx_and_channel):
        ctx, channel, tracker = ctx_and_channel

        await update_submission_tracker(channel, ctx, extra_text="\nSubmissions are closed!")

        content = tracker.edit.await_args.kwargs["content"]
        assert content.endswith("`0/2` submissions for the round.\nSubmissions are closed!")

    async def test_without_a_tracker_message_nothing_happens(self, ctx_and_channel):
        ctx, channel, _ = ctx_and_channel
        ctx.round.status_message_id = None

        await update_submission_tracker(channel, ctx)

        channel.fetch_message.assert_not_called()

    @pytest.mark.parametrize("error", [
        discord.NotFound(mock.Mock(status=404, reason="Not Found"), "Unknown Message"),
        discord.Forbidden(mock.Mock(status=403, reason="Forbidden"), "Missing Access"),
    ])
    async def test_a_deleted_or_unreachable_tracker_is_logged_not_raised(self, ctx_and_channel, error, caplog):
        ctx, channel, _ = ctx_and_channel
        channel.fetch_message.side_effect = error

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await update_submission_tracker(channel, ctx)

        assert "Could not update the submissions tracker message" in caplog.text
