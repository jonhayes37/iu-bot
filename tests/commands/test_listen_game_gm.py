"""Tests for commands/listen_game_gm.py: the Game Master's commands."""

import logging
from unittest import mock

import discord
import pytest

from commands.listen_game_gm import (
    _sync_missing_videos, listen_game_create, listen_game_gm_approve_playlist, listen_game_gm_force_start_round,
    listen_game_gm_force_submit, listen_game_gm_reject_song, listen_game_gm_remove_player,
    listen_game_gm_skip_turn, listen_game_gm_swap_players, listen_game_gm_sync_playlist, listen_game_start
)
from config import Database
from db.listen_game import (
    GameStatus, RoundStatus, Submission, create_game_db, get_current_round_db, get_game_by_status_db,
    get_ordered_players_db, get_registered_players_db, get_round_db,
    get_user_submission_db, register_player_db, set_round_theme_db, update_game_start_message_db,
    update_round_playlist_db, update_round_status_message_db, upsert_submission_db
)
from services.listen_game_playlist import PlaylistOutcome
from services.youtube import QuotaExceededError
from testsupport.listen_game import GM, SUB_GM, reveal_ready_round, start_game
from ui.listen_game import JoinGameView

NOT_FOUND = discord.NotFound(mock.Mock(status=404, reason="Not Found"), "Unknown")
FORBIDDEN = discord.Forbidden(mock.Mock(status=403, reason="Forbidden"), "Missing Permissions")
VIDEO = "dQw4w9WgXcQ"


@pytest.fixture(autouse=True)
def _listen_game_database(databases):
    databases(Database.LISTEN_GAME)


def _submitting_round(players=(101, 102, 103), playlist="PLround"):
    """A game whose round is taking submissions (101 is listening). Returns (game_id, round_id)."""
    game_id = start_game(players)
    round_id = get_current_round_db(game_id).round_id
    set_round_theme_db(round_id, "Rain songs")
    if playlist:
        update_round_playlist_db(round_id, playlist)
    return game_id, round_id


def _last_reply(interaction):
    return interaction.sent[-1].content


class TestEveryCommandIsChannelRestricted:
    """The GM commands only work in #listen-game."""

    @pytest.mark.parametrize("command, args", [
        (listen_game_create, lambda s: (s.members[2],)),
        (listen_game_start, lambda s: ()),
        (listen_game_gm_sync_playlist, lambda s: ()),
        (listen_game_gm_reject_song, lambda s: (s.members[102], "why")),
        (listen_game_gm_skip_turn, lambda s: (s.members[101], "why")),
        (listen_game_gm_remove_player, lambda s: (s.members[102], "why")),
        (listen_game_gm_force_start_round, lambda s: ("",)),
        (listen_game_gm_force_submit, lambda s: (s.members[102], "https://youtu.be/x")),
        (listen_game_gm_approve_playlist, lambda s: ()),
    ])
    async def test_other_channels_are_refused(self, listen_server, make_channel, command, args):
        interaction = listen_server.interaction(1)
        interaction.channel = make_channel("general")

        await command.callback(interaction, *args(listen_server))

        assert interaction.sent[0].content == "This command can only be used in the #listen-game channel."


class TestCreateGame:
    """/listen-game-create opens registration."""

    async def test_opens_registration_with_a_join_button_and_pings_the_players_role(self, listen_server):
        interaction = listen_server.interaction(1)

        await listen_game_create.callback(interaction, listen_server.members[2], 3)

        game = get_game_by_status_db(GameStatus.REGISTRATION)
        assert (game.gm_id, game.sub_gm_id, game.max_round_days) == (1, 2, 3)
        [post] = interaction.sent
        assert post.content == listen_server.guild.roles[0].mention
        assert post.embed.title == "🎵 A New Listen Game is Starting!"
        assert f"{listen_server.members[1].mention} has opened registration for a new game." in post.embed.description
        assert "**Max Round Duration:** 3 Days" in post.embed.description
        assert isinstance(post.kwargs["view"], JoinGameView)

    async def test_no_deadline_is_described_as_gm_managed(self, listen_server):
        interaction = listen_server.interaction(1)

        await listen_game_create.callback(interaction, listen_server.members[2], None)

        assert "**Max Round Duration:** None (GM Managed)" in interaction.sent[0].embed.description

    async def test_the_gm_cannot_be_their_own_substitute(self, listen_server):
        interaction = listen_server.interaction(1)

        await listen_game_create.callback(interaction, listen_server.members[1], None)

        assert interaction.sent[0].content == "❌ The substitute GM cannot be yourself."
        assert get_game_by_status_db(GameStatus.REGISTRATION) is None

    async def test_a_second_game_cannot_be_opened_while_one_is_running(self, listen_server):
        create_game_db(GM, SUB_GM, None)
        interaction = listen_server.interaction(1)

        await listen_game_create.callback(interaction, listen_server.members[2], None)

        assert interaction.sent[0].content == \
            "❌ There is already an active game running! Finish it before creating a new one."

    async def test_a_server_without_the_role_still_opens_registration(self, listen_server):
        listen_server.guild.roles = []
        interaction = listen_server.interaction(1)

        await listen_game_create.callback(interaction, listen_server.members[2], None)

        assert interaction.sent[0].content is None and interaction.sent[0].embed is not None


class TestStartGame:
    """/listen-game-start closes registration and pins the turn order."""

    @staticmethod
    def _registered(players=(101, 102, 103)):
        game_id = create_game_db(GM, SUB_GM, None)
        for user_id in players:
            register_player_db(game_id, user_id)
        return game_id

    async def test_no_game_in_registration(self, listen_server):
        interaction = listen_server.interaction(1)

        await listen_game_start.callback(interaction)

        assert (interaction.sent[0].content, interaction.sent[0].ephemeral) == \
            ("❌ Cannot find a game in the registration phase.", True)

    @pytest.mark.parametrize("players", [(), (101,)])
    async def test_at_least_two_players_are_needed(self, listen_server, players):
        self._registered(players)
        interaction = listen_server.interaction(1)

        await listen_game_start.callback(interaction)

        assert interaction.sent[0].content == \
            f"❌ You need at least 2 players to start! Currently have {len(players)}."
        assert get_game_by_status_db(GameStatus.REGISTRATION) is not None

    async def test_starts_the_game_and_announces_the_turn_order_and_first_listener(self, listen_server):
        game_id = self._registered()
        interaction = listen_server.interaction(1)

        await listen_game_start.callback(interaction)

        order = get_ordered_players_db(game_id)
        assert get_game_by_status_db(GameStatus.PLAYING).game_id == game_id
        [post] = interaction.sent
        assert post.content == f"<@{order[0]}>"
        assert post.embed.title == "The Listen Game has officially begun!"
        assert f"Our first listener is <@{order[0]}>!" in post.embed.description
        for position, user_id in enumerate(order, start=1):
            assert f"{position}. {listen_server.members[user_id].mention}" in post.embed.description
        assert get_current_round_db(game_id).host_id == order[0]

    async def test_the_turn_order_message_is_pinned_and_remembered(self, listen_server):
        self._registered()
        interaction = listen_server.interaction(1)
        posted = await interaction.original_response()
        interaction.original_response.side_effect = None
        interaction.original_response.return_value = posted

        await listen_game_start.callback(interaction)

        posted.pin.assert_awaited_once_with(reason="Listen Game Turn Order")
        assert get_game_by_status_db(GameStatus.PLAYING).game_start_message_id == posted.id

    @pytest.mark.parametrize("error, text", [
        (FORBIDDEN, "Bot lacks permission to pin messages"),
        (discord.HTTPException(mock.Mock(status=500, reason="x"), "boom"), "Failed to pin the turn order message")])
    async def test_a_failure_to_pin_is_logged_and_the_game_still_starts(self, listen_server, caplog, error, text):
        self._registered()
        interaction = listen_server.interaction(1)
        posted = await interaction.original_response()
        posted.pin.side_effect = error
        interaction.original_response.side_effect = None
        interaction.original_response.return_value = posted

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await listen_game_start.callback(interaction)

        assert get_game_by_status_db(GameStatus.PLAYING) is not None
        assert text in caplog.text

    async def test_a_game_that_was_started_in_the_meantime_is_reported(self, listen_server, monkeypatch):
        self._registered()
        monkeypatch.setattr("commands.listen_game_gm.start_game_db", lambda _: None)
        interaction = listen_server.interaction(1)

        await listen_game_start.callback(interaction)

        assert interaction.sent[0].content == "❌ The game could not be started. It may have already been started."


class TestSyncPlaylist:
    """/listen-game-gm-sync-playlist adds any submitted songs missing from the YouTube playlist."""

    @pytest.fixture(name="youtube", autouse=True)
    def _youtube(self, monkeypatch):
        calls = mock.Mock()
        calls.playlist_ids.return_value = set()
        calls.add.return_value = True
        monkeypatch.setattr("commands.listen_game_gm.get_playlist_video_ids", calls.playlist_ids)
        monkeypatch.setattr("commands.listen_game_gm.add_video_to_playlist", calls.add)
        return calls

    @staticmethod
    def _songs(*video_ids):
        _, round_id = _submitting_round()
        for index, video_id in enumerate(video_ids):
            upsert_submission_db(round_id, 102 + index, video_id, f"Song {video_id}")
        return round_id

    async def test_it_defers_privately_first_because_youtube_is_slow(self, listen_server):
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    async def test_no_active_game(self, listen_server):
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert _last_reply(interaction) == "⚠️ There is no active game right now."

    async def test_a_round_without_a_playlist_yet(self, listen_server):
        _submitting_round(playlist=None)
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert _last_reply(interaction) == "⚠️ No YouTube playlist has been generated for this round yet."

    async def test_a_round_without_songs(self, listen_server):
        _submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert _last_reply(interaction) == "ℹ️ There are no submissions in the database to sync."

    async def test_a_playlist_that_is_up_to_date(self, listen_server, youtube):
        self._songs("vidA", "vidB")
        youtube.playlist_ids.return_value = {"vidA", "vidB"}
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert _last_reply(interaction) == "✅ The YouTube playlist is completely up to date with the database!"
        youtube.add.assert_not_called()

    async def test_missing_songs_are_added(self, listen_server, youtube):
        self._songs("vidA", "vidB", "vidC")
        youtube.playlist_ids.return_value = {"vidA"}
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert sorted(c.args[1] for c in youtube.add.call_args_list) == ["vidB", "vidC"]
        assert all(c.args[0] == "PLround" for c in youtube.add.call_args_list)
        assert _last_reply(interaction) == "🔄 **Sync Complete!**\nAdded 2 missing videos to the playlist."

    async def test_songs_that_cannot_be_added_are_counted(self, listen_server, youtube):
        self._songs("vidA", "vidB")
        youtube.add.side_effect = lambda _, video: video == "vidA"
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert "Added 1 missing videos" in _last_reply(interaction)
        assert "⚠️ Failed to add 1 videos (they may be private or deleted)." in _last_reply(interaction)

    async def test_running_out_of_quota_halts_the_sync_and_alerts_the_gm(self, listen_server, youtube):
        self._songs("vidA", "vidB")
        youtube.add.side_effect = [True, QuotaExceededError(RuntimeError("limit"))]
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert "**Sync halted: YouTube API Quota Exceeded.**" in _last_reply(interaction)
        [alert] = listen_server.dms(1)
        assert alert.startswith("🚨 **Listen Game Alert: YouTube API Quota Exceeded!**")

    async def test_quota_exhausted_when_reading_the_playlist_changes_nothing(self, listen_server, youtube):
        self._songs("vidA")
        youtube.playlist_ids.side_effect = QuotaExceededError(RuntimeError("limit"))
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert "Nothing was changed. Please run this command again tomorrow." in _last_reply(interaction)
        youtube.add.assert_not_called()

    async def test_an_unreadable_playlist_is_not_treated_as_empty(self, listen_server, youtube):
        self._songs("vidA")
        youtube.playlist_ids.return_value = None
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert "nothing was changed" in _last_reply(interaction)
        youtube.add.assert_not_called()

    def test_the_worker_reports_added_failed_and_quota(self, monkeypatch):
        outcomes = iter([True, False, QuotaExceededError(RuntimeError("limit")), True])

        def add(*_):
            result = next(outcomes)
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr("commands.listen_game_gm.add_video_to_playlist", add)
        songs = [Submission(1, i, f"v{i}", "t") for i in range(4)]

        assert _sync_missing_videos("PL", songs) == (1, 1, True)      # it stops at the quota error

    def test_the_worker_with_nothing_to_do(self):
        assert _sync_missing_videos("PL", []) == (0, 0, False)


class TestRejectSong:
    """/listen-game-gm-reject-song removes a submission and tells the player."""

    @pytest.fixture(name="youtube", autouse=True)
    def _youtube(self, monkeypatch):
        remove = mock.Mock(return_value=True)
        monkeypatch.setattr("commands.listen_game_gm.remove_video_from_playlist", remove)
        return remove

    async def test_only_while_submissions_are_open(self, listen_server):
        start_game()
        interaction = listen_server.interaction(1)

        await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "dupe")

        assert _last_reply(interaction) == "⚠️ Submissions are closed! You cannot reject a song at this phase."

    async def test_a_player_who_has_not_submitted(self, listen_server):
        _submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "dupe")

        assert _last_reply(interaction) == "⚠️ Member 102 has not submitted a song for this round."

    async def test_removes_the_song_from_the_round_and_the_playlist_and_tells_the_player_why(
            self, listen_server, youtube):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 102, "vidA", "Song A")
        interaction = listen_server.interaction(1)

        await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "It's a duplicate")

        assert get_user_submission_db(round_id, 102) is None
        youtube.assert_called_once_with("PLround", "vidA")
        [dm] = listen_server.dms(102)
        assert "rejected your submission for the current round (`Song A`)" in dm
        assert "**Reason:** It's a duplicate" in dm
        assert _last_reply(interaction) == "✅ **Success!** Removed `Song A`. Player was DMed the reason."

    async def test_a_player_with_closed_dms_is_flagged_for_a_manual_ping(self, listen_server):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 102, "vidA", "Song A")
        listen_server.blocked(102)
        interaction = listen_server.interaction(1)

        await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "dupe")

        assert "Player has DMs disabled. You will need to ping them in the channel manually." in \
            _last_reply(interaction)

    async def test_a_round_with_no_playlist_yet_skips_the_youtube_step(self, listen_server, youtube):
        _, round_id = _submitting_round(playlist=None)
        upsert_submission_db(round_id, 102, "vidA", "Song A")
        interaction = listen_server.interaction(1)

        await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "dupe")

        youtube.assert_not_called()
        assert get_user_submission_db(round_id, 102) is None

    async def test_a_failure_to_remove_it_from_youtube_is_logged_but_the_rejection_stands(
            self, listen_server, youtube, caplog):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 102, "vidA", "Song A")
        youtube.return_value = False
        interaction = listen_server.interaction(1)

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "dupe")

        assert "Failed to remove video vidA from YT playlist" in caplog.text
        assert get_user_submission_db(round_id, 102) is None


class TestSkipTurn:
    """/listen-game-gm-skip-turn moves on from a listener who isn't playing."""

    async def test_no_active_game(self, listen_server):
        interaction = listen_server.interaction(1)

        await listen_game_gm_skip_turn.callback(interaction, listen_server.members[101], "away")

        assert _last_reply(interaction) == "⚠️ There is no active game right now."

    async def test_only_the_current_listener_can_be_skipped(self, listen_server):
        start_game()
        interaction = listen_server.interaction(1)

        await listen_game_gm_skip_turn.callback(interaction, listen_server.members[102], "away")

        assert _last_reply(interaction) == \
            "❌ Member 102 is not the current listener. The current listener is Member 101."

    async def test_a_reveal_in_progress_cannot_be_skipped(self, listen_server):
        game_id = start_game()
        reveal_ready_round(game_id)
        interaction = listen_server.interaction(1)

        await listen_game_gm_skip_turn.callback(interaction, listen_server.members[101], "away")

        assert "results are already being revealed" in _last_reply(interaction)
        assert get_round_db(get_current_round_db(game_id).round_id).status is RoundStatus.REVEALING

    async def test_skips_the_turn_tells_the_player_and_announces_the_next_listener(self, listen_server):
        game_id = start_game()
        first_round = get_current_round_db(game_id).round_id
        interaction = listen_server.interaction(1)

        await listen_game_gm_skip_turn.callback(interaction, listen_server.members[101], "On holiday")

        assert get_round_db(first_round).status is RoundStatus.SKIPPED
        assert get_current_round_db(game_id).host_id == 102
        assert "**Reason:** On holiday" in listen_server.dms(101)[0]
        assert _last_reply(interaction) == \
            "✅ **Success!** Member 101's turn has been skipped. Player was DMed the reason."
        announcements = [m.content for m in listen_server.channel.sent]
        assert announcements[0] == "⚠️ **Attention!** The Game Master has skipped <@101>'s turn."
        assert announcements[1].startswith("⏭️ The turn order has advanced! The new listener is <@102>!")

    async def test_a_player_with_closed_dms_is_flagged(self, listen_server):
        start_game()
        listen_server.blocked(101)
        interaction = listen_server.interaction(1)

        await listen_game_gm_skip_turn.callback(interaction, listen_server.members[101], "away")

        assert "Player has DMs disabled. You will need to ping them manually." in _last_reply(interaction)

    async def test_skipping_the_last_listener_ends_the_game_with_the_leaderboard(self, listen_server):
        game_id = start_game((101, 102))
        listen_server.channel.sent.clear()
        await listen_game_gm_skip_turn.callback(listen_server.interaction(1), listen_server.members[101], "away")
        listen_server.channel.sent.clear()

        await listen_game_gm_skip_turn.callback(listen_server.interaction(1), listen_server.members[102], "away")

        texts = [m.content for m in listen_server.channel.sent]
        assert texts[1] == "🏆 **The game has concluded early due to a turn skip! Calculating final scores...**"
        assert texts[2].startswith("🏆 **Listen Game - Final Leaderboard** 🏆")
        assert get_game_by_status_db(GameStatus.FINISHED).game_id == game_id


class TestRemovePlayer:
    """/listen-game-gm-remove-player takes a player out of the game."""

    @pytest.fixture(name="youtube", autouse=True)
    def _youtube(self, monkeypatch):
        remove = mock.Mock(return_value=True)
        monkeypatch.setattr("commands.listen_game_gm.remove_video_from_playlist", remove)
        return remove

    async def test_no_game(self, listen_server):
        interaction = listen_server.interaction(1)

        await listen_game_gm_remove_player.callback(interaction, listen_server.members[102], "gone")

        assert _last_reply(interaction) == "⚠️ There is no active game right now."

    async def test_someone_who_is_not_in_the_game(self, listen_server):
        start_game((101, 102))
        interaction = listen_server.interaction(1)

        await listen_game_gm_remove_player.callback(interaction, listen_server.members[103], "gone")

        assert _last_reply(interaction) == "⚠️ Member 103 is not in the current game."

    async def test_the_current_listener_must_be_skipped_first(self, listen_server):
        start_game()
        interaction = listen_server.interaction(1)

        await listen_game_gm_remove_player.callback(interaction, listen_server.members[101], "gone")

        assert "is the current listener! Please use `/listen-game-gm-skip-turn` first" in _last_reply(interaction)
        assert 101 in get_registered_players_db(get_game_by_status_db(GameStatus.PLAYING).game_id)

    async def test_removes_a_player_informs_them_and_announces_it(self, listen_server):
        game_id = start_game()
        interaction = listen_server.interaction(1)

        await listen_game_gm_remove_player.callback(interaction, listen_server.members[103], "Inactive")

        assert get_registered_players_db(game_id) == [101, 102]
        assert "**Reason:** Inactive" in listen_server.dms(103)[0]
        assert _last_reply(interaction) == "✅ **Success!** Member 103 has been removed from the game. Player was DMed."
        assert listen_server.channel.sent[0].content == "The Game Master has removed Member 103 from the game."

    async def test_a_player_can_be_removed_during_registration(self, listen_server):
        game_id = create_game_db(GM, SUB_GM, None)
        register_player_db(game_id, 102)
        interaction = listen_server.interaction(1)

        await listen_game_gm_remove_player.callback(interaction, listen_server.members[102], "gone")

        assert get_registered_players_db(game_id) == []

    async def test_their_song_is_removed_from_the_round_and_the_playlist_while_submissions_are_open(
            self, listen_server, youtube):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 103, "vidC", "Song C")
        interaction = listen_server.interaction(1)

        await listen_game_gm_remove_player.callback(interaction, listen_server.members[103], "gone")

        assert get_user_submission_db(round_id, 103) is None
        youtube.assert_called_once_with("PLround", "vidC")

    async def test_removing_the_last_missing_player_closes_the_round_and_tells_the_listener(self, listen_server):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 102, "vidB", "Song B")        # only 103 hasn't submitted
        interaction = listen_server.interaction(1)

        await listen_game_gm_remove_player.callback(interaction, listen_server.members[103], "gone")

        assert get_round_db(round_id).status is RoundStatus.RANKING
        [dm] = listen_server.dms(101)
        assert dm.startswith("🎉 **All submissions are in for your Listen Game round!**")
        assert "https://www.youtube.com/playlist?list=PLround" in dm

    async def test_a_player_with_closed_dms_is_flagged(self, listen_server):
        start_game()
        listen_server.blocked(103)
        interaction = listen_server.interaction(1)

        await listen_game_gm_remove_player.callback(interaction, listen_server.members[103], "gone")

        assert "Player has DMs disabled." in _last_reply(interaction)


class TestForceStartRound:
    """/listen-game-gm-force-start-round closes submissions, skipping the players who haven't sent a song."""

    async def test_only_while_submissions_are_open(self, listen_server):
        start_game()
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_start_round.callback(interaction, "<@102> <@103>")

        assert _last_reply(interaction) == "⚠️ The round is not currently in the submission phase."

    async def test_the_gm_must_name_exactly_the_players_who_are_missing(self, listen_server):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 102, "vidB", "Song B")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_start_round.callback(interaction, "<@102>")

        content = _last_reply(interaction)
        assert content.startswith("❌ **Validation Failed!** Your tags do not match the outstanding players.")
        assert "**Actually missing:** <@103>" in content
        assert get_round_db(round_id).status is RoundStatus.SUBMITTING

    @pytest.mark.parametrize("tags", ["", "<@102>", "<@101> <@102> <@103>", "<@102> <@103> <@999>"])
    async def test_naming_too_few_or_too_many_is_refused(self, listen_server, tags):
        _, round_id = _submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_start_round.callback(interaction, tags)

        assert "Validation Failed" in _last_reply(interaction)
        assert get_round_db(round_id).status is RoundStatus.SUBMITTING

    async def test_naming_the_right_players_closes_the_round_and_tells_the_listener(self, listen_server):
        _, round_id = _submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_start_round.callback(interaction, "<@102> <@!103>")

        assert get_round_db(round_id).status is RoundStatus.RANKING
        [dm] = listen_server.dms(101)
        assert dm.startswith("🚨 **Round Force-Closed!**")
        assert "https://www.youtube.com/playlist?list=PLround" in dm
        assert _last_reply(interaction) == "✅ **Success!** Round forced closed. Listener notified via DM."

    async def test_when_nobody_is_missing_the_gm_is_told_no_one(self, listen_server):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 102, "vidB", "Song B")
        upsert_submission_db(round_id, 103, "vidC", "Song C")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_start_round.callback(interaction, "<@102>")

        assert "**Actually missing:** No one!" in _last_reply(interaction)

    async def test_a_listener_with_closed_dms_is_flagged(self, listen_server):
        _submitting_round()
        listen_server.blocked(101)
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_start_round.callback(interaction, "<@102> <@103>")

        assert _last_reply(interaction) == "✅ **Success!** Round forced closed. Listener has DMs disabled."

    async def test_the_submissions_tracker_is_updated(self, listen_server):
        _, round_id = _submitting_round()
        update_round_status_message_db(round_id, 9001)
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_start_round.callback(interaction, "<@102> <@103>")

        interaction.channel.fetch_message.assert_awaited_once_with(9001)

    async def test_a_round_that_moved_on_meanwhile_is_reported(self, listen_server, monkeypatch):
        _submitting_round()
        monkeypatch.setattr("commands.listen_game_gm.close_round_db", lambda _: False)
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_start_round.callback(interaction, "<@102> <@103>")

        assert _last_reply(interaction) == "⚠️ The round has already moved on, so nothing was changed."


class TestForceSubmit:
    """/listen-game-gm-force-submit puts a song in for a player."""

    @pytest.fixture(name="youtube", autouse=True)
    def _youtube(self, monkeypatch):
        calls = mock.Mock()
        calls.title.return_value = "Forced Song"
        calls.put.return_value = (PlaylistOutcome.ADDED, "PLround")
        monkeypatch.setattr("commands.listen_game_gm.get_video_title", calls.title)
        monkeypatch.setattr("commands.listen_game_gm.put_song_in_round_playlist", calls.put)
        return calls

    URL = f"https://youtu.be/{VIDEO}"

    async def test_only_while_submissions_are_open(self, listen_server):
        start_game()
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction) == "⚠️ The round is not currently in the submission phase."

    async def test_nothing_can_be_submitted_for_the_listener(self, listen_server):
        _submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[101], self.URL)

        assert _last_reply(interaction) == "❌ You cannot submit a song for the current listener."

    async def test_an_invalid_link(self, listen_server):
        _submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], "not a link")

        assert _last_reply(interaction) == "❌ Invalid YouTube URL."

    async def test_a_video_that_cannot_be_found(self, listen_server, youtube):
        _submitting_round()
        youtube.title.return_value = None
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction) == "❌ Could not fetch that video. It may be private or deleted."

    async def test_submits_the_song_for_the_player_and_tells_them(self, listen_server):
        _, round_id = _submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        saved = get_user_submission_db(round_id, 102)
        assert (saved.video_id, saved.raw_title) == (VIDEO, "Forced Song")
        assert listen_server.dms(102) == [
            "✅ The GM has forcefully submitted your song `Forced Song` for the Listen Game!"]
        assert _last_reply(interaction) == "✅ **Success!** `Forced Song` accepted for Member 102. Player was DMed."

    async def test_replacing_an_earlier_song_removes_it_from_the_playlist_and_says_updated(
            self, listen_server, youtube):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 102, "oldvideo123", "Old Song")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert youtube.put.call_args.args[3] == "oldvideo123"
        assert _last_reply(interaction) == \
            "🔄 **Updated!** Swapped submission to `Forced Song` for Member 102. Player was DMed."

    async def test_the_last_missing_song_closes_the_round_and_tells_the_listener(self, listen_server):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 103, "vidC", "Song C")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert get_round_db(round_id).status is RoundStatus.RANKING
        assert listen_server.dms(101)[0].startswith("🎉 **All submissions are in for your Listen Game round!**")

    async def test_replacing_a_song_does_not_close_the_round_again(self, listen_server):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 102, "old", "Old")
        upsert_submission_db(round_id, 103, "vidC", "Song C")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert get_round_db(round_id).status is RoundStatus.SUBMITTING

    async def test_a_playlist_that_cannot_be_made(self, listen_server, youtube):
        _, round_id = _submitting_round()
        youtube.put.return_value = (PlaylistOutcome.CREATE_FAILED, None)
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction) == "❌ Could not create the YouTube playlist for this round. Check the logs."
        assert get_user_submission_db(round_id, 102) is None

    async def test_a_song_youtube_will_not_take(self, listen_server, youtube):
        _, round_id = _submitting_round()
        youtube.put.return_value = (PlaylistOutcome.ADD_FAILED, "PLround")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction) == "❌ Failed to add video to the playlist. It may be blocked or private."
        assert get_user_submission_db(round_id, 102) is None

    async def test_running_out_of_quota_still_saves_the_song_and_says_to_sync_later(self, listen_server, youtube):
        _, round_id = _submitting_round()
        youtube.put.return_value = (PlaylistOutcome.QUOTA_EXCEEDED, "PLround")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert get_user_submission_db(round_id, 102) is not None
        assert "Run `/listen-game-gm-sync-playlist` tomorrow" in _last_reply(interaction)
        assert len(listen_server.dms(102)) == 1

    async def test_a_player_with_closed_dms_is_flagged(self, listen_server):
        _submitting_round()
        listen_server.blocked(102)
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction).endswith("Player has DMs disabled.")


class TestApprovePlaylist:
    """/listen-game-gm-approve-playlist closes the round once everyone has submitted."""

    async def test_only_while_submissions_are_open(self, listen_server):
        start_game()
        interaction = listen_server.interaction(1)

        await listen_game_gm_approve_playlist.callback(interaction)

        assert _last_reply(interaction) == "⚠️ The round is not in the submission phase."

    async def test_it_cannot_be_approved_while_songs_are_missing(self, listen_server):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 102, "vidB", "Song B")
        interaction = listen_server.interaction(1)

        await listen_game_gm_approve_playlist.callback(interaction)

        assert _last_reply(interaction) == "⚠️ Cannot approve yet! Not all players have submitted a song."
        assert get_round_db(round_id).status is RoundStatus.SUBMITTING

    @pytest.fixture(name="complete")
    def _complete(self):
        _, round_id = _submitting_round()
        upsert_submission_db(round_id, 102, "vidB", "Song B")
        upsert_submission_db(round_id, 103, "vidC", "Song C")
        return round_id

    async def test_approving_closes_the_round_and_sends_the_playlist_to_the_listener(self, listen_server, complete):
        interaction = listen_server.interaction(1)

        await listen_game_gm_approve_playlist.callback(interaction)

        assert get_round_db(complete).status is RoundStatus.RANKING
        [dm] = listen_server.dms(101)
        assert dm.startswith("🎉 **All submissions are in for your Listen Game ruleset!**")
        assert "https://www.youtube.com/playlist?list=PLround" in dm
        assert _last_reply(interaction) == ("✅ **Success!** The round has been closed and the playlist sent to "
                                            f"{listen_server.members[101].mention}. Listener notified via DM.")

    @pytest.mark.usefixtures("complete")
    async def test_it_is_announced_publicly(self, listen_server):
        interaction = listen_server.interaction(1)

        await listen_game_gm_approve_playlist.callback(interaction)

        [announcement] = listen_server.channel.sent
        assert announcement.content.startswith("✅ **Playlist Approved!**")
        assert listen_server.members[101].mention in announcement.content

    @pytest.mark.usefixtures("complete")
    async def test_a_listener_with_closed_dms_is_flagged(self, listen_server):
        listen_server.blocked(101)
        interaction = listen_server.interaction(1)

        await listen_game_gm_approve_playlist.callback(interaction)

        assert _last_reply(interaction).endswith("Listener has DMs disabled.")

    async def test_missing_permission_to_announce_is_logged_and_the_round_still_closes(
            self, listen_server, complete, caplog):
        listen_server.channel.send.side_effect = FORBIDDEN
        interaction = listen_server.interaction(1)

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await listen_game_gm_approve_playlist.callback(interaction)

        assert "Failed to send public approval message" in caplog.text
        assert get_round_db(complete).status is RoundStatus.RANKING

    @pytest.mark.usefixtures("complete")
    async def test_a_round_that_moved_on_meanwhile_is_reported(self, listen_server, monkeypatch):
        monkeypatch.setattr("commands.listen_game_gm.close_round_db", lambda _: False)
        interaction = listen_server.interaction(1)

        await listen_game_gm_approve_playlist.callback(interaction)

        assert _last_reply(interaction) == "⚠️ The round has already moved on, so nothing was changed."


class TestSwapPlayers:
    """/listen-game-gm-swap-players reorders the players who haven't been listener yet."""

    async def test_no_game_being_played(self, listen_server):
        interaction = listen_server.interaction(1)

        await listen_game_gm_swap_players.callback(interaction, listen_server.members[102], listen_server.members[103])

        assert (interaction.sent[0].content, interaction.sent[0].ephemeral) == \
            ("⚠️ There is no active Listen Game currently running.", True)

    async def test_a_player_cannot_be_swapped_with_themselves(self, listen_server):
        start_game()
        interaction = listen_server.interaction(1)

        await listen_game_gm_swap_players.callback(interaction, listen_server.members[102], listen_server.members[102])

        assert interaction.sent[0].content == "❌ You cannot swap a player with themselves."

    @pytest.mark.parametrize("first, second, text", [
        (101, 102, "❌ Cannot swap: Both players must be scheduled *after* the current host's turn."),
        (102, 999, "❌ One or both specified players are not registered in this game."),
    ])
    async def test_swaps_the_game_refuses_are_explained_privately(self, listen_server, first, second, text):
        start_game()
        listen_server.members[999] = mock.Mock(id=999, mention="<@999>")
        interaction = listen_server.interaction(1)

        await listen_game_gm_swap_players.callback(interaction, listen_server.members[first],
                                                   listen_server.members[second])

        assert (interaction.sent[0].content, interaction.sent[0].ephemeral) == (text, True)

    async def test_swaps_two_players_and_confirms_publicly(self, listen_server):
        game_id = start_game()
        interaction = listen_server.interaction(1)

        await listen_game_gm_swap_players.callback(interaction, listen_server.members[102], listen_server.members[103])

        assert get_ordered_players_db(game_id) == [101, 103, 102]
        interaction.response.defer.assert_awaited_once_with(ephemeral=False)
        assert interaction.sent[-1].content == (
            f"🔄 {listen_server.members[102].mention} and {listen_server.members[103].mention} have swapped positions "
            "in the turn order. The pinned turn order message has been updated!")

    async def test_the_pinned_turn_order_message_is_rewritten(self, listen_server):
        game_id = start_game()
        update_game_start_message_db(game_id, 555)
        pinned = mock.MagicMock(spec=discord.Message, edit=mock.AsyncMock())
        pinned.embeds = [discord.Embed(description="old text")]
        interaction = listen_server.interaction(1)
        interaction.channel.fetch_message = mock.AsyncMock(return_value=pinned)

        await listen_game_gm_swap_players.callback(interaction, listen_server.members[102], listen_server.members[103])

        interaction.channel.fetch_message.assert_awaited_once_with(555)
        description = pinned.edit.await_args.kwargs["embed"].description
        assert "**Turn Order:**\n1. " in description
        assert description.index(listen_server.members[103].mention) < description.index(
            listen_server.members[102].mention)
        assert "Our first listener is <@101>!" in description

    @pytest.mark.parametrize("error", [NOT_FOUND, discord.HTTPException(mock.Mock(status=500, reason="x"), "boom")])
    async def test_a_pinned_message_that_cannot_be_updated_does_not_undo_the_swap(self, listen_server, error, caplog):
        game_id = start_game()
        update_game_start_message_db(game_id, 555)
        interaction = listen_server.interaction(1)
        interaction.channel.fetch_message = mock.AsyncMock(side_effect=error)

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await listen_game_gm_swap_players.callback(interaction, listen_server.members[102],
                                                       listen_server.members[103])

        assert get_ordered_players_db(game_id) == [101, 103, 102]
        assert "turn order message" in caplog.text or "Game start message" in caplog.text
