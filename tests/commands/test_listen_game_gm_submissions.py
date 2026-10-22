"""Tests for commands/listen_game_gm.py: the GM commands that change a round's songs (sync, reject, force-submit).

The other GM commands are tested in test_listen_game_gm.py.
"""

import logging
from unittest import mock

import pytest

from commands.listen_game_gm import (
    _sync_missing_videos, listen_game_gm_force_submit, listen_game_gm_reject_song, LEDGER_SENT,
    NOT_REMOVED_FROM_PLAYLIST, YOUTUBE_UNAVAILABLE, listen_game_gm_sync_playlist
)
from config import Database
from db.listen_game import (
    RoundStatus, Submission, get_round_db, get_user_submission_db, update_round_status_message_db,
    upsert_submission_db
)
from services.listen_game import YOUTUBE_QUOTA_USED_UP
from services.listen_game_playlist import PlaylistOutcome
from services.youtube import QuotaExceededError, YouTubeUnavailableError
from testsupport.listen_game import GM, start_game, submitting_round

VIDEO = "dQw4w9WgXcQ"


@pytest.fixture(autouse=True)
def _listen_game_database(databases):
    databases(Database.LISTEN_GAME)


def _last_reply(interaction):
    return interaction.sent[-1].content


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
        _, round_id = submitting_round()
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
        submitting_round(playlist=None)
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert _last_reply(interaction) == "⚠️ No YouTube playlist has been generated for this round yet."

    async def test_a_round_without_songs(self, listen_server):
        submitting_round()
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

    async def test_youtube_unreachable_when_reading_the_playlist_changes_nothing(self, listen_server, youtube):
        self._songs("vidA")
        youtube.playlist_ids.side_effect = YouTubeUnavailableError("network down")
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert _last_reply(interaction) == YOUTUBE_UNAVAILABLE
        youtube.add.assert_not_called()

    async def test_losing_youtube_mid_sync_reports_what_was_added_and_to_run_it_again(self, listen_server, youtube):
        self._songs("vidA", "vidB")
        youtube.add.side_effect = [True, YouTubeUnavailableError("network down")]
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert "Added 1 missing videos" in _last_reply(interaction)
        assert "**Sync halted: the bot lost its connection to YouTube.**" in _last_reply(interaction)
        assert listen_server.dms(1) == []      # nothing to wait for until tomorrow, unlike the quota

    async def test_an_unreadable_playlist_is_not_treated_as_empty(self, listen_server, youtube):
        self._songs("vidA")
        youtube.playlist_ids.return_value = None
        interaction = listen_server.interaction(1)

        await listen_game_gm_sync_playlist.callback(interaction)

        assert "nothing was changed" in _last_reply(interaction)
        youtube.add.assert_not_called()

    @pytest.mark.parametrize("stop", [QuotaExceededError(RuntimeError("limit")), YouTubeUnavailableError("down")])
    def test_the_worker_reports_added_failed_and_what_stopped_it(self, monkeypatch, stop):
        outcomes = iter([True, False, stop, True])

        def add(*_):
            result = next(outcomes)
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr("commands.listen_game_gm.add_video_to_playlist", add)
        songs = [Submission(1, i, f"v{i}", "t") for i in range(4)]

        assert _sync_missing_videos("PL", songs) == (1, 1, stop)      # it stops at the error

    def test_the_worker_with_nothing_to_do(self):
        assert _sync_missing_videos("PL", []) == (0, 0, None)


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
        submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "dupe")

        assert _last_reply(interaction) == "⚠️ Member 102 has not submitted a song for this round."

    async def test_the_submissions_counter_goes_down(self, listen_server):
        _, round_id = submitting_round()
        upsert_submission_db(round_id, 102, "vidA", "Song A")
        update_round_status_message_db(round_id, 9001)
        interaction = listen_server.interaction(1)
        tracker = mock.Mock(edit=mock.AsyncMock())
        interaction.channel.fetch_message = mock.AsyncMock(return_value=tracker)

        await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "It's a duplicate")

        interaction.channel.fetch_message.assert_awaited_once_with(9001)
        assert "`0/2` submissions" in tracker.edit.await_args.kwargs["content"]

    async def test_removes_the_song_from_the_round_and_the_playlist_and_tells_the_player_why(
            self, listen_server, youtube):
        _, round_id = submitting_round()
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
        _, round_id = submitting_round()
        upsert_submission_db(round_id, 102, "vidA", "Song A")
        listen_server.blocked(102)
        interaction = listen_server.interaction(1)

        await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "dupe")

        assert "Player has DMs disabled. You will need to ping them in the channel manually." in \
            _last_reply(interaction)

    async def test_a_round_with_no_playlist_yet_skips_the_youtube_step(self, listen_server, youtube):
        _, round_id = submitting_round(playlist=None)
        upsert_submission_db(round_id, 102, "vidA", "Song A")
        interaction = listen_server.interaction(1)

        await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "dupe")

        youtube.assert_not_called()
        assert get_user_submission_db(round_id, 102) is None

    async def test_a_failure_to_remove_it_from_youtube_is_logged_but_the_rejection_stands(
            self, listen_server, youtube, caplog):
        _, round_id = submitting_round()
        upsert_submission_db(round_id, 102, "vidA", "Song A")
        youtube.return_value = False
        interaction = listen_server.interaction(1)

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "dupe")

        assert "Failed to remove video vidA from YT playlist" in caplog.text
        assert get_user_submission_db(round_id, 102) is None
        assert _last_reply(interaction).endswith(NOT_REMOVED_FROM_PLAYLIST)    # so the GM can take it out by hand

    async def test_youtube_being_unreachable_still_rejects_and_tells_the_player(self, listen_server, youtube):
        _, round_id = submitting_round()
        upsert_submission_db(round_id, 102, "vidA", "Song A")
        youtube.side_effect = YouTubeUnavailableError("network down")
        interaction = listen_server.interaction(1)

        await listen_game_gm_reject_song.callback(interaction, listen_server.members[102], "dupe")

        assert get_user_submission_db(round_id, 102) is None
        assert len(listen_server.dms(102)) == 1
        assert _last_reply(interaction) == \
            "✅ **Success!** Removed `Song A`. Player was DMed the reason." + NOT_REMOVED_FROM_PLAYLIST


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
        submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[101], self.URL)

        assert _last_reply(interaction) == "❌ You cannot submit a song for the current listener."

    async def test_an_invalid_link(self, listen_server):
        submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], "not a link")

        assert _last_reply(interaction) == "❌ Invalid YouTube URL."

    async def test_a_video_that_cannot_be_found(self, listen_server, youtube):
        submitting_round()
        youtube.title.return_value = None
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction) == "❌ Could not fetch that video. It may be private or deleted."

    async def test_a_used_up_quota_says_so_instead_of_blaming_the_video(self, listen_server, youtube):
        _, round_id = submitting_round()
        youtube.title.side_effect = QuotaExceededError(ValueError("quotaExceeded"))
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction) == YOUTUBE_QUOTA_USED_UP
        assert get_user_submission_db(round_id, 102) is None

    async def test_youtube_being_unreachable_says_so_instead_of_blaming_the_video(self, listen_server, youtube):
        _, round_id = submitting_round()
        youtube.title.side_effect = YouTubeUnavailableError("invalid_grant")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction) == YOUTUBE_UNAVAILABLE
        assert get_user_submission_db(round_id, 102) is None
        youtube.put.assert_not_called()

    async def test_losing_youtube_while_adding_to_the_playlist_saves_nothing(self, listen_server, youtube):
        _, round_id = submitting_round()
        youtube.put.return_value = (PlaylistOutcome.YOUTUBE_UNAVAILABLE, "PLround")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction) == YOUTUBE_UNAVAILABLE
        assert get_user_submission_db(round_id, 102) is None

    async def test_submits_the_song_for_the_player_and_tells_them(self, listen_server):
        _, round_id = submitting_round()
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        saved = get_user_submission_db(round_id, 102)
        assert (saved.video_id, saved.raw_title) == (VIDEO, "Forced Song")
        assert listen_server.dms(102) == [
            "✅ The GM has forcefully submitted your song `Forced Song` for the Listen Game!"]
        assert _last_reply(interaction) == "✅ **Success!** `Forced Song` accepted for Member 102. Player was DMed."

    async def test_replacing_an_earlier_song_removes_it_from_the_playlist_and_says_updated(
            self, listen_server, youtube):
        _, round_id = submitting_round()
        upsert_submission_db(round_id, 102, "oldvideo123", "Old Song")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert youtube.put.call_args.args[3] == "oldvideo123"
        assert _last_reply(interaction) == \
            "🔄 **Updated!** Swapped submission to `Forced Song` for Member 102. Player was DMed."

    async def test_the_last_missing_song_sends_the_gm_the_ledger_to_review(self, listen_server):
        _, round_id = submitting_round()
        upsert_submission_db(round_id, 103, "vidC", "Song C")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert get_round_db(round_id).status is RoundStatus.SUBMITTING        # the GM approves it, not the bot
        [ledger] = listen_server.dms(GM)
        assert ledger.startswith("**Listen Game: All Submissions Are In!**")
        assert "• **Member 102**: `Forced Song`" in ledger and "• **Member 103**: `Song C`" in ledger
        assert listen_server.dms(101) == []
        assert _last_reply(interaction).endswith(LEDGER_SENT)

    async def test_replacing_a_song_does_not_send_the_ledger_again(self, listen_server):
        _, round_id = submitting_round()
        upsert_submission_db(round_id, 102, "old", "Old")
        upsert_submission_db(round_id, 103, "vidC", "Song C")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert get_round_db(round_id).status is RoundStatus.SUBMITTING
        assert listen_server.dms(GM) == []
        assert LEDGER_SENT not in _last_reply(interaction)

    async def test_a_playlist_that_cannot_be_made(self, listen_server, youtube):
        _, round_id = submitting_round()
        youtube.put.return_value = (PlaylistOutcome.CREATE_FAILED, None)
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction) == "❌ Could not create the YouTube playlist for this round. Check the logs."
        assert get_user_submission_db(round_id, 102) is None

    async def test_a_song_youtube_will_not_take(self, listen_server, youtube):
        _, round_id = submitting_round()
        youtube.put.return_value = (PlaylistOutcome.ADD_FAILED, "PLround")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction) == "❌ Failed to add video to the playlist. It may be blocked or private."
        assert get_user_submission_db(round_id, 102) is None

    async def test_running_out_of_quota_still_saves_the_song_and_says_to_sync_later(self, listen_server, youtube):
        _, round_id = submitting_round()
        youtube.put.return_value = (PlaylistOutcome.QUOTA_EXCEEDED, "PLround")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert get_user_submission_db(round_id, 102) is not None
        assert _last_reply(interaction).startswith("✅ **Success!** `Forced Song` accepted for Member 102.")
        assert "Run `/listen-game-gm-sync-playlist` tomorrow" in _last_reply(interaction)
        assert len(listen_server.dms(102)) == 1

    async def test_running_out_of_quota_on_the_last_song_still_sends_the_ledger_with_a_sync_reminder(
            self, listen_server, youtube):
        _, round_id = submitting_round()
        upsert_submission_db(round_id, 103, "vidC", "Song C")
        update_round_status_message_db(round_id, 9001)
        youtube.put.return_value = (PlaylistOutcome.QUOTA_EXCEEDED, "PLround")
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        [ledger] = listen_server.dms(GM)
        assert "Run `/listen-game-gm-sync-playlist` once the quota resets, before approving" in ledger
        assert _last_reply(interaction).endswith(LEDGER_SENT)
        interaction.channel.fetch_message.assert_awaited_once_with(9001)

    async def test_a_player_with_closed_dms_is_flagged(self, listen_server):
        submitting_round()
        listen_server.blocked(102)
        interaction = listen_server.interaction(1)

        await listen_game_gm_force_submit.callback(interaction, listen_server.members[102], self.URL)

        assert _last_reply(interaction).endswith("Player has DMs disabled.")
