"""Tests for commands/listen_game.py: the commands players and listeners use."""

from unittest import mock

import pytest

from commands.listen_game import listen_game_set_theme, listen_game_submit_ranking, submit_song
from config import Database
from db.listen_game import (
    RoundStatus, close_round_db, get_current_round_db, get_round_db, get_user_submission_db, save_ranking_pick_db,
    set_round_theme_db, update_round_ruleset_message_db, update_round_status_message_db, upsert_submission_db
)
from services.listen_game_playlist import PlaylistOutcome
from testsupport.listen_game import reveal_ready_round, start_game
from ui.listen_game import ListenGameRankingView, SetThemeModal

VIDEO = "dQw4w9WgXcQ"
URL = f"https://youtu.be/{VIDEO}"


@pytest.fixture(autouse=True)
def _listen_game_database(databases):
    databases(Database.LISTEN_GAME)


def _round_id(game_id):
    return get_current_round_db(game_id).round_id


def _reply(interaction):
    return interaction.sent[-1].content


class TestPostRuleset:
    """/listen-game-post-ruleset opens the ruleset form for the current listener."""

    async def test_only_in_the_game_channel(self, listen_server, make_channel):
        interaction = listen_server.interaction(101)
        interaction.channel = make_channel("general")

        await listen_game_set_theme.callback(interaction)

        assert interaction.sent[0].content == "This command can only be used in the #listen-game channel."

    async def test_no_active_game(self, listen_server):
        interaction = listen_server.interaction(101)

        await listen_game_set_theme.callback(interaction)

        assert _reply(interaction) == "⚠️ There is no active game right now."

    async def test_only_the_current_listener_can_post_it_and_who_we_are_waiting_for_is_named(self, listen_server):
        start_game()
        interaction = listen_server.interaction(102)

        await listen_game_set_theme.callback(interaction)

        assert (interaction.sent[0].content, interaction.sent[0].ephemeral) == (
            f"❌ You are not the listener for this round! We are waiting on {listen_server.members[101].mention}.",
            True)

    async def test_a_listener_who_left_the_server_is_described_generically(self, listen_server):
        start_game()
        listen_server.guild.members = [m for m in listen_server.guild.members if m.id != 101]
        interaction = listen_server.interaction(102)

        await listen_game_set_theme.callback(interaction)

        assert "We are waiting on the current listener." in _reply(interaction)

    async def test_the_listener_gets_an_empty_form_for_a_new_round(self, listen_server):
        game_id = start_game()
        interaction = listen_server.interaction(101)

        await listen_game_set_theme.callback(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, SetThemeModal)
        assert (modal.game_id, modal.round_id, modal.ruleset_msg_id) == (game_id, _round_id(game_id), None)
        assert modal.theme_text.default is None

    async def test_an_open_round_can_have_its_ruleset_edited_with_the_old_text_and_post_id(self, listen_server):
        game_id = start_game()
        round_id = _round_id(game_id)
        set_round_theme_db(round_id, "Rain songs")
        update_round_ruleset_message_db(round_id, 4242)
        interaction = listen_server.interaction(101)

        await listen_game_set_theme.callback(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        assert (modal.theme_text.default, modal.ruleset_msg_id) == ("Rain songs", 4242)

    async def test_the_ruleset_is_locked_once_everyone_has_submitted(self, listen_server):
        game_id = start_game()
        round_id = _round_id(game_id)
        set_round_theme_db(round_id, "Rain songs")
        upsert_submission_db(round_id, 102, "v1", "t1")
        upsert_submission_db(round_id, 103, "v2", "t2")
        interaction = listen_server.interaction(101)

        await listen_game_set_theme.callback(interaction)

        assert _reply(interaction) == \
            "❌ All players have already submitted their songs! You can no longer change the ruleset."
        interaction.response.send_modal.assert_not_awaited()

    async def test_the_ruleset_is_locked_after_submissions_close(self, listen_server):
        game_id = start_game()
        round_id = _round_id(game_id)
        set_round_theme_db(round_id, "Rain songs")
        close_round_db(round_id)
        interaction = listen_server.interaction(101)

        await listen_game_set_theme.callback(interaction)

        assert "You can no longer change the ruleset" in _reply(interaction)

    async def test_a_round_that_is_not_waiting_for_a_ruleset_is_refused(self, listen_server, execute):
        game_id = start_game()
        execute(Database.LISTEN_GAME, "UPDATE listen_rounds SET status = 'ranking' WHERE round_id = ?",
                _round_id(game_id))
        interaction = listen_server.interaction(101)

        await listen_game_set_theme.callback(interaction)

        assert _reply(interaction) == "⚠️ The game is not currently waiting for a ruleset."


class TestSubmitSong:
    """/listen-game-submit-song."""

    @pytest.fixture(name="youtube", autouse=True)
    def _youtube(self, monkeypatch):
        calls = mock.Mock()
        calls.title.return_value = "IU - Good Day"
        calls.put.return_value = (PlaylistOutcome.ADDED, "PLround")
        monkeypatch.setattr("commands.listen_game.get_video_title", calls.title)
        monkeypatch.setattr("commands.listen_game.put_song_in_round_playlist", calls.put)
        return calls

    @staticmethod
    def _open_round(players=(101, 102, 103)):
        game_id = start_game(players)
        round_id = _round_id(game_id)
        set_round_theme_db(round_id, "Rain songs")
        return game_id, round_id

    async def test_only_in_the_game_channel(self, listen_server, make_channel):
        interaction = listen_server.interaction(102)
        interaction.channel = make_channel("general")

        await submit_song.callback(interaction, URL)

        assert interaction.sent[0].content == "This command can only be used in the #listen-game channel."

    async def test_it_is_acknowledged_first_because_youtube_is_slow(self, listen_server):
        self._open_round()
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    async def test_no_active_game(self, listen_server):
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert _reply(interaction) == "⚠️ There is no active game right now."

    async def test_submissions_must_be_open(self, listen_server):
        start_game()
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert _reply(interaction) == "⚠️ The round is not currently accepting submissions."

    async def test_the_listener_does_not_submit(self, listen_server):
        self._open_round()
        interaction = listen_server.interaction(101)

        await submit_song.callback(interaction, URL)

        assert _reply(interaction) == "❌ You are the listener! You don't submit a song for your own round."

    async def test_an_invalid_link(self, listen_server):
        self._open_round()
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, "not a youtube link")

        assert _reply(interaction) == "❌ Invalid YouTube URL."

    async def test_a_video_that_cannot_be_found(self, listen_server, youtube):
        self._open_round()
        youtube.title.return_value = None
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert _reply(interaction) == "❌ Could not fetch that video. It may be private or deleted."

    async def test_a_song_someone_else_already_submitted_is_refused(self, listen_server):
        _, round_id = self._open_round()
        upsert_submission_db(round_id, 103, VIDEO, "IU - Good Day")
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert _reply(interaction).startswith("❌ **Song Already Claimed!**")
        assert get_user_submission_db(round_id, 102) is None

    async def test_resubmitting_the_same_video_changes_nothing(self, listen_server, youtube):
        _, round_id = self._open_round()
        upsert_submission_db(round_id, 102, VIDEO, "IU - Good Day")
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert _reply(interaction) == "⚠️ You have already submitted this exact video!"
        youtube.put.assert_not_called()

    async def test_a_new_song_goes_in_the_playlist_the_database_and_the_gm_is_told(self, listen_server, youtube):
        _, round_id = self._open_round()
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        saved = get_user_submission_db(round_id, 102)
        assert (saved.video_id, saved.raw_title) == (VIDEO, "IU - Good Day")
        assert youtube.put.call_args.args[2:] == (VIDEO, None)
        assert _reply(interaction) == "✅ **Success!** Your song `IU - Good Day` has been accepted."
        [dm] = listen_server.dms(1)
        assert dm.startswith("🎵 **New Listen Game Submission!**")
        assert "**Player:** Member 102" in dm and f"**URL:** {URL}" in dm and "`IU - Good Day`" in dm

    async def test_changing_a_song_removes_the_old_one_from_the_playlist_and_says_updated(self, listen_server, youtube):
        _, round_id = self._open_round()
        upsert_submission_db(round_id, 102, "oldvideo123", "Old Song")
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert youtube.put.call_args.args[3] == "oldvideo123"
        assert _reply(interaction) == "🔄 **Updated!** Your submission has been swapped to `IU - Good Day`."
        assert get_user_submission_db(round_id, 102).video_id == VIDEO

    async def test_the_substitute_gm_is_told_when_the_gm_is_the_listener(self, listen_server):
        game_id = start_game((1, 102, 103))                 # the GM (1) is listening
        set_round_theme_db(_round_id(game_id), "Rain songs")
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert len(listen_server.dms(2)) == 1 and listen_server.dms(1) == []

    async def test_the_submissions_counter_is_refreshed(self, listen_server):
        _, round_id = self._open_round()
        update_round_status_message_db(round_id, 9001)
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        interaction.channel.fetch_message.assert_awaited_once_with(9001)

    async def test_the_last_song_sends_the_gm_the_ledger_to_review(self, listen_server):
        _, round_id = self._open_round()
        upsert_submission_db(round_id, 103, "vidC", "Song C")
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        ledger = listen_server.dms(1)[1]
        assert ledger.startswith("**Listen Game: All Submissions Are In!**")
        assert "https://www.youtube.com/playlist?list=PLround" in ledger
        assert "• **Member 103**: `Song C`" in ledger and "• **Member 102**: `IU - Good Day`" in ledger
        assert "`/listen-game-gm-approve-playlist`" in ledger
        assert get_round_db(round_id).status is RoundStatus.SUBMITTING        # the GM approves it, not the bot

    async def test_changing_a_song_after_the_round_is_full_does_not_send_the_ledger_again(self, listen_server):
        _, round_id = self._open_round()
        upsert_submission_db(round_id, 102, "old", "Old")
        upsert_submission_db(round_id, 103, "vidC", "Song C")
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert len(listen_server.dms(1)) == 1

    async def test_a_playlist_that_cannot_be_made(self, listen_server, youtube):
        _, round_id = self._open_round()
        youtube.put.return_value = (PlaylistOutcome.CREATE_FAILED, None)
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert _reply(interaction) == "❌ Internal Error: Could not create YouTube playlist. Contact the GM."
        assert get_user_submission_db(round_id, 102) is None

    async def test_a_song_youtube_will_not_take(self, listen_server, youtube):
        _, round_id = self._open_round()
        youtube.put.return_value = (PlaylistOutcome.ADD_FAILED, "PLround")
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert _reply(interaction) == "❌ Failed to add video to the playlist. It may be blocked or private."
        assert get_user_submission_db(round_id, 102) is None

    async def test_running_out_of_quota_keeps_the_song_and_tells_the_player_and_the_gm(self, listen_server, youtube):
        _, round_id = self._open_round()
        youtube.put.return_value = (PlaylistOutcome.QUOTA_EXCEEDED, "PLround")
        interaction = listen_server.interaction(102)

        await submit_song.callback(interaction, URL)

        assert get_user_submission_db(round_id, 102) is not None
        assert "YouTube API limits have been reached for today" in _reply(interaction)
        assert len(listen_server.dms(1)) == 1


class TestSubmitRanking:
    """/listen-game-submit-ranking opens the ranking screen, or resumes an interrupted reveal."""

    @pytest.fixture(name="reveal", autouse=True)
    def _reveal(self, monkeypatch):
        started = mock.Mock(return_value=True)
        monkeypatch.setattr("commands.listen_game.start_reveal", started)
        return started

    @staticmethod
    def _ranking_round():
        game_id = start_game()
        round_id = _round_id(game_id)
        set_round_theme_db(round_id, "Rain songs")
        upsert_submission_db(round_id, 102, "vid102", "Song 102")
        upsert_submission_db(round_id, 103, "vid103", "Song 103")
        close_round_db(round_id)
        return game_id, round_id

    async def test_only_in_the_game_channel(self, listen_server, make_channel):
        interaction = listen_server.interaction(101)
        interaction.channel = make_channel("general")

        await listen_game_submit_ranking.callback(interaction)

        assert interaction.sent[0].content == "This command can only be used in the #listen-game channel."

    async def test_no_active_game(self, listen_server):
        interaction = listen_server.interaction(101)

        await listen_game_submit_ranking.callback(interaction)

        assert _reply(interaction) == "⚠️ There is no active game right now."

    async def test_submissions_still_open(self, listen_server):
        game_id = start_game()
        set_round_theme_db(_round_id(game_id), "Rain songs")
        interaction = listen_server.interaction(101)

        await listen_game_submit_ranking.callback(interaction)

        assert _reply(interaction) == \
            "⚠️ Submissions are still open! Wait for the deadline or ask the GM to close the round."

    async def test_only_the_listener_can_rank(self, listen_server):
        self._ranking_round()
        interaction = listen_server.interaction(102)

        await listen_game_submit_ranking.callback(interaction)

        assert _reply(interaction) == "❌ Only the listener of the current round can submit the rankings."

    async def test_a_round_with_no_songs(self, listen_server):
        game_id = start_game()
        round_id = _round_id(game_id)
        set_round_theme_db(round_id, "Rain songs")
        close_round_db(round_id)
        interaction = listen_server.interaction(101)

        await listen_game_submit_ranking.callback(interaction)

        assert _reply(interaction) == "❌ No submissions found for this round."

    async def test_the_listener_gets_a_private_ranking_screen_for_the_songs(self, listen_server):
        game_id, round_id = self._ranking_round()
        interaction = listen_server.interaction(101)

        await listen_game_submit_ranking.callback(interaction)

        [reply] = interaction.sent
        assert reply.ephemeral
        view = reply.kwargs["view"]
        assert isinstance(view, ListenGameRankingView)
        assert (view.game_id, view.round_id, view.listen_channel_id) == (game_id, round_id, listen_server.channel.id)
        assert sorted(s.user_id for s in view.unranked_submissions) == [102, 103]
        assert reply.embed.title == "Listen Game Rankings"

    async def test_picks_made_before_a_restart_are_picked_back_up(self, listen_server):
        _, round_id = self._ranking_round()
        save_ranking_pick_db(round_id, 103, 2, "already ranked")
        interaction = listen_server.interaction(101)

        await listen_game_submit_ranking.callback(interaction)

        view = interaction.sent[0].kwargs["view"]
        assert [(r.submission.user_id, r.commentary) for r in view.ranked_submissions] == [(103, "already ranked")]

    async def test_a_reveal_cut_short_by_a_restart_is_resumed_by_the_listener(self, listen_server, reveal):
        game_id = start_game()
        round_id = reveal_ready_round(game_id)
        interaction = listen_server.interaction(101)

        await listen_game_submit_ranking.callback(interaction)

        reveal.assert_called_once_with(interaction.channel, round_id)
        assert (interaction.sent[0].content, interaction.sent[0].ephemeral) == \
            ("▶️ Resuming the reveal in this channel.", True)

    async def test_the_gm_can_resume_it_too(self, listen_server, reveal):
        reveal_ready_round(start_game())
        interaction = listen_server.interaction(1)

        await listen_game_submit_ranking.callback(interaction)

        reveal.assert_called_once()

    async def test_the_substitute_gm_resumes_it_when_the_gm_is_the_listener(self, listen_server, reveal):
        reveal_ready_round(start_game((1, 102, 103)))
        interaction = listen_server.interaction(2)

        await listen_game_submit_ranking.callback(interaction)

        reveal.assert_called_once()

    async def test_other_players_cannot_resume_it(self, listen_server, reveal):
        reveal_ready_round(start_game())
        interaction = listen_server.interaction(102)

        await listen_game_submit_ranking.callback(interaction)

        assert _reply(interaction) == "❌ Only the listener or the GM can resume the reveal."
        reveal.assert_not_called()

    async def test_a_reveal_that_is_already_running_is_left_alone(self, listen_server, reveal):
        reveal_ready_round(start_game())
        reveal.return_value = False
        interaction = listen_server.interaction(101)

        await listen_game_submit_ranking.callback(interaction)

        assert _reply(interaction) == "⏳ The reveal is already in progress."
