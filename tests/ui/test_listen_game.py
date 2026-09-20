"""Tests for ui/listen_game.py: joining a game, setting the ruleset, and ranking the songs."""

import logging
import sqlite3
from unittest import mock

import discord
import pytest

from config import Database, Role
from db.listen_game import (
    RankingPick, RoundStatus, Submission, close_round_db, create_game_db, get_current_round_db,
    get_game_leaderboard_db, get_ranking_picks_db, get_registered_players_db, get_round_db,
    get_round_results_db, register_player_db, save_ranking_pick_db, set_round_theme_db, upsert_submission_db
)
from ui.base import DATABASE_ERROR
from ui.listen_game import (
    CommentaryModal, ConfirmRankingButton, JoinGameView, ListenGameRankingView, RankedSong, RankingSelect,
    RankSingleSongButton, SetThemeModal, StartOverButton, build_rankings_embed
)
from testsupport.listen_game import GM, SUB_GM, start_game
from testsupport.ui import fill

NOT_FOUND = discord.NotFound(mock.Mock(status=404, reason="Not Found"), "Unknown Message")


@pytest.fixture(autouse=True)
def _listen_game_database(databases):
    databases(Database.LISTEN_GAME)


def _http_error():
    return discord.HTTPException(mock.Mock(status=500, reason="Server Error"), "boom")


def _labels(view):
    return {child.label: child for child in view.children if hasattr(child, "label")}


class TestJoinGameView:
    """The Join and Leave buttons on the registration post."""

    @staticmethod
    def _open_registration(max_round_days=None):
        return create_game_db(GM, SUB_GM, max_round_days)

    async def test_the_buttons_have_stable_ids_so_they_survive_a_restart(self):
        view = JoinGameView()

        assert view.timeout is None
        assert {c.custom_id for c in view.children} == {"join_listen_game", "leave_listen_game"}

    async def test_joining_with_no_registration_open(self, interaction):
        await JoinGameView().join_button.callback(interaction)

        assert (interaction.sent[0].content, interaction.sent[0].ephemeral) == \
            ("⚠️ No registration session is active.", True)

    async def test_leaving_with_no_registration_open(self, interaction):
        await JoinGameView().leave_button.callback(interaction)

        assert interaction.sent[0].content == "⚠️ No registration session is active."

    async def test_joining_registers_the_player_and_refreshes_the_post(self, interaction, make_guild):
        game_id = self._open_registration(max_round_days=3)
        interaction.guild = make_guild()

        await JoinGameView().join_button.callback(interaction)

        assert get_registered_players_db(game_id) == [interaction.user.id]
        [update] = interaction.sent
        assert update.via == "edit"
        embed = update.embed
        assert embed.title == "🎵 A New Listen Game is Starting!"
        assert f"<@{GM}> has opened registration for a new game." in embed.description
        assert "**Max Round Duration:** 3 Days" in embed.description
        assert embed.fields[0].name == "👥 1 Registered Players"
        assert embed.fields[0].value == f"• <@{interaction.user.id}>"

    async def test_no_deadline_is_described_as_gm_managed(self, interaction, make_guild):
        self._open_registration(max_round_days=None)
        interaction.guild = make_guild()

        await JoinGameView().join_button.callback(interaction)

        assert "**Max Round Duration:** None (GM Managed)" in interaction.sent[0].embed.description

    async def test_the_list_names_members_who_are_in_the_server(self, interaction, make_guild, make_member):
        game_id = self._open_registration()
        friend = make_member(user_id=555, name="Friend")
        interaction.guild = make_guild()
        interaction.guild.members = [friend]
        register_player_db(game_id, 555)
        register_player_db(game_id, 666)          # left the server

        await JoinGameView().join_button.callback(interaction)

        value = interaction.sent[0].embed.fields[0].value
        assert "• <@555>" in value and "• <@666>" in value and f"• <@{interaction.user.id}>" in value
        assert interaction.sent[0].embed.fields[0].name == "👥 3 Registered Players"

    async def test_joining_twice_says_so_and_changes_nothing(self, interaction, make_guild):
        game_id = self._open_registration()
        register_player_db(game_id, interaction.user.id)
        interaction.guild = make_guild()

        await JoinGameView().join_button.callback(interaction)

        assert (interaction.sent[0].content, interaction.sent[0].ephemeral) == ("You are already registered!", True)
        assert len(get_registered_players_db(game_id)) == 1

    async def test_a_new_player_is_given_the_player_role(self, interaction, make_guild):
        self._open_registration()
        interaction.guild = make_guild(roles=(Role.LISTEN_GAME_PLAYER,))

        await JoinGameView().join_button.callback(interaction)

        interaction.user.add_roles.assert_awaited_once_with(interaction.guild.roles[0])

    async def test_someone_who_already_has_the_role_is_not_given_it_again(self, interaction, make_guild):
        self._open_registration()
        interaction.guild = make_guild(roles=(Role.LISTEN_GAME_PLAYER,))
        interaction.user.roles = [interaction.guild.roles[0]]

        await JoinGameView().join_button.callback(interaction)

        interaction.user.add_roles.assert_not_awaited()

    async def test_a_server_without_the_role_still_lets_them_join(self, interaction, make_guild):
        game_id = self._open_registration()
        interaction.guild = make_guild(roles=())

        await JoinGameView().join_button.callback(interaction)

        assert get_registered_players_db(game_id) == [interaction.user.id]
        interaction.user.add_roles.assert_not_awaited()

    @pytest.mark.parametrize("error, expected", [
        (discord.Forbidden(mock.Mock(status=403, reason="Forbidden"), "Missing Permissions"), "lacks permission"),
        (_http_error(), "HTTPException while assigning role"),
    ])
    async def test_a_failure_to_give_the_role_is_logged_and_they_are_still_registered(
            self, interaction, make_guild, error, expected, caplog):
        game_id = self._open_registration()
        interaction.guild = make_guild(roles=(Role.LISTEN_GAME_PLAYER,))
        interaction.user.add_roles.side_effect = error

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await JoinGameView().join_button.callback(interaction)

        assert expected in caplog.text
        assert get_registered_players_db(game_id) == [interaction.user.id]
        assert interaction.sent[0].via == "edit"

    async def test_leaving_removes_the_player_and_refreshes_the_post(self, interaction, make_guild):
        game_id = self._open_registration()
        register_player_db(game_id, interaction.user.id)
        register_player_db(game_id, 777)
        interaction.guild = make_guild()

        await JoinGameView().leave_button.callback(interaction)

        assert get_registered_players_db(game_id) == [777]
        assert interaction.sent[0].embed.fields[0].name == "👥 1 Registered Players"

    async def test_the_last_player_leaving_shows_an_empty_list(self, interaction, make_guild):
        game_id = self._open_registration()
        register_player_db(game_id, interaction.user.id)
        interaction.guild = make_guild()

        await JoinGameView().leave_button.callback(interaction)

        field = interaction.sent[0].embed.fields[0]
        assert (field.name, field.value) == ("👥 Registered Players (0)", "No one has joined yet. Be the first!")

    async def test_leaving_without_having_joined(self, interaction, make_guild):
        self._open_registration()
        interaction.guild = make_guild()

        await JoinGameView().leave_button.callback(interaction)

        assert (interaction.sent[0].content, interaction.sent[0].ephemeral) == \
            ("You aren't registered for this game.", True)

    async def test_a_database_failure_is_reported(self, interaction, execute):
        execute(Database.LISTEN_GAME, "DROP TABLE listen_games")
        view = JoinGameView()

        with pytest.raises(Exception) as caught:
            await view.join_button.callback(interaction)
        await view.on_error(interaction, caught.value, view.join_button)

        assert interaction.sent[0].content == DATABASE_ERROR


class TestSetThemeModal:
    """The listener's form for the round's ruleset."""

    @pytest.fixture(name="round_ids")
    def _round_ids(self):
        game_id = start_game()
        return game_id, get_current_round_db(game_id).round_id

    @staticmethod
    def _modal(round_ids, existing_theme=None, ruleset_msg_id=None):
        return SetThemeModal(round_ids[0], round_ids[1], existing_theme, ruleset_msg_id)

    async def test_the_form_starts_empty_or_with_the_existing_ruleset(self, round_ids):
        assert self._modal(round_ids).theme_text.default is None
        assert self._modal(round_ids, "My rules").theme_text.default == "My rules"

    async def test_an_existing_ruleset_does_not_leak_into_the_next_form(self, round_ids):
        self._modal(round_ids, "My rules")

        assert self._modal(round_ids).theme_text.default is None

    async def test_a_new_ruleset_is_saved_and_announced_with_the_player_role(self, interaction, make_guild, round_ids):
        interaction.guild = make_guild(roles=(Role.LISTEN_GAME_PLAYER,))
        modal = self._modal(round_ids)
        fill(modal.theme_text, "Songs about rain")

        await modal.on_submit(interaction)

        saved = get_round_db(round_ids[1])
        assert (saved.theme, saved.status) == ("Songs about rain", RoundStatus.SUBMITTING)
        announcement = interaction.sent[0]
        role_mention = interaction.guild.roles[0].mention
        assert announcement.content == \
            f"{role_mention} The new ruleset has been posted. It's time to submit your songs!"
        embed = announcement.embed
        assert (embed.title, embed.description) == ("🎧 New Listen Game Round Started!", "Songs about rain")
        assert embed.author.name == f"Listener: {interaction.user.display_name}"
        assert embed.footer.text == "Use `/listen-game-submit-song` to submit your track!"
        assert announcement.kwargs["allowed_mentions"].roles is True

    async def test_the_announcement_and_a_submissions_tracker_are_remembered(self, interaction, make_guild, round_ids):
        interaction.guild = make_guild()
        modal = self._modal(round_ids)
        fill(modal.theme_text, "Songs about rain")
        original = await interaction.original_response()
        interaction.original_response.side_effect = None
        interaction.original_response.return_value = original

        await modal.on_submit(interaction)

        saved = get_round_db(round_ids[1])
        assert saved.ruleset_message_id == original.id
        [tracker] = interaction.channel.sent
        assert tracker.content == "🎧 **Round Status:** We are at `0/2` submissions for the round."
        assert saved.status_message_id is not None

    async def test_a_server_without_the_role_still_gets_the_announcement(self, interaction, make_guild, round_ids):
        interaction.guild = make_guild(roles=())
        modal = self._modal(round_ids)
        fill(modal.theme_text, "rules")

        await modal.on_submit(interaction)

        assert interaction.sent[0].content.startswith(" The new ruleset has been posted.")

    async def test_failing_to_look_up_the_announcement_is_logged_and_the_round_still_starts(
            self, interaction, make_guild, round_ids, caplog):
        interaction.guild = make_guild()
        interaction.original_response.side_effect = _http_error()
        modal = self._modal(round_ids)
        fill(modal.theme_text, "rules")

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await modal.on_submit(interaction)

        assert "Failed to fetch and save ruleset message ID" in caplog.text
        assert get_round_db(round_ids[1]).status is RoundStatus.SUBMITTING
        assert len(interaction.channel.sent) == 1

    async def test_editing_the_ruleset_updates_the_original_post_and_announces_the_change(
            self, interaction, make_guild, round_ids):
        interaction.guild = make_guild(roles=(Role.LISTEN_GAME_PLAYER,))
        set_round_theme_db(round_ids[1], "Old rules")
        modal = self._modal(round_ids, "Old rules", ruleset_msg_id=4242)
        fill(modal.theme_text, "New rules")

        await modal.on_submit(interaction)

        interaction.channel.fetch_message.assert_awaited_once_with(4242)
        assert get_round_db(round_ids[1]).theme == "New rules"
        [notice] = interaction.sent
        assert notice.content == (f"📢 {interaction.guild.roles[0].mention} "
                                  f"**The ruleset has been updated by {interaction.user.mention}!**")
        assert interaction.channel.sent == []          # no second tracker

    async def test_editing_when_the_original_post_was_deleted_still_saves_the_ruleset(
            self, interaction, make_guild, round_ids):
        interaction.guild = make_guild()
        interaction.channel.fetch_message.side_effect = NOT_FOUND
        set_round_theme_db(round_ids[1], "Old rules")
        modal = self._modal(round_ids, "Old rules", ruleset_msg_id=4242)
        fill(modal.theme_text, "New rules")

        await modal.on_submit(interaction)

        assert get_round_db(round_ids[1]).theme == "New rules"
        assert interaction.sent[0].content.startswith("⚠️ The ruleset was saved, but the original message was deleted")
        assert interaction.sent[0].ephemeral

    async def test_a_round_that_is_past_submissions_refuses_the_ruleset(self, interaction, make_guild, round_ids):
        interaction.guild = make_guild()
        set_round_theme_db(round_ids[1], "Old rules")
        close_round_db(round_ids[1])
        modal = self._modal(round_ids)
        fill(modal.theme_text, "Too late")

        await modal.on_submit(interaction)

        assert interaction.sent[0].content == "⚠️ This round is no longer accepting a ruleset, so nothing was changed."
        assert interaction.sent[0].ephemeral
        assert get_round_db(round_ids[1]).theme == "Old rules"


def _submissions(*titles):
    """Songs from players 201, 202, ... with the given titles."""
    return [Submission(round_id=1, user_id=200 + i, video_id=f"vid{200 + i}", raw_title=title)
            for i, title in enumerate(titles, start=1)]


class TestBuildRankingsEmbed:
    """The listener's summary of their ranking so far."""

    @staticmethod
    def _ranked(count, commentary="great"):
        subs = _submissions(*[f"Song {i}" for i in range(1, count + 1)])
        return [RankedSong(sub, rank=count - i, commentary=commentary) for i, sub in enumerate(subs)]

    def test_lists_each_ranked_song_with_its_commentary(self):
        embed = build_rankings_embed(self._ranked(2), all_ranked=False)

        assert (embed.title, embed.description) == ("Listen Game Rankings", "Here are your rankings so far:")
        assert [(f.name, f.value) for f in embed.fields] == [("#2 - Song 1", "great"), ("#1 - Song 2", "great")]
        assert embed.footer.text is None

    def test_when_every_song_is_ranked_it_asks_for_confirmation(self):
        embed = build_rankings_embed(self._ranked(2), all_ranked=True)

        assert embed.description == "✅ **All songs ranked!** Review your list and click Confirm to publish."
        assert embed.color.value == 0x2ecc71

    def test_long_commentary_is_shortened_so_the_embed_fits_and_the_footer_says_so(self):
        embed = build_rankings_embed(self._ranked(25, commentary="x" * 1000), all_ranked=True)

        assert len(embed) <= 6000
        assert all(len(f.value) <= 1024 for f in embed.fields)
        assert embed.fields[0].value.endswith("…")
        assert embed.footer.text == "Long commentary is shortened in this preview. The full text will be published."

    def test_short_commentary_is_left_alone(self):
        embed = build_rankings_embed(self._ranked(3, commentary="y" * 500), all_ranked=False)

        assert all(f.value == "y" * 500 for f in embed.fields)
        assert embed.footer.text is None

    def test_long_titles_are_cut_to_the_field_name_limit(self):
        ranked = [RankedSong(_submissions("t" * 400)[0], rank=1, commentary="c")]

        assert len(build_rankings_embed(ranked, all_ranked=False).fields[0].name) == 256


class TestCommentaryModal:
    """The form asking for thoughts on one song."""

    async def test_is_titled_for_the_place_and_labelled_with_the_song(self):
        modal = CommentaryModal(mock.Mock(), _submissions("A" * 80)[0], 3)

        assert modal.title == "3rd Place Commentary"
        assert modal.commentary.to_component_dict()["label"] == "For " + "A" * 37
        assert modal.commentary.required and modal.commentary.max_length == 1000

    async def test_submitting_hands_the_pick_to_the_ranking_view(self, interaction):
        view = mock.Mock(rank_song=mock.AsyncMock())
        song = _submissions("Song")[0]
        modal = CommentaryModal(view, song, 2)
        fill(modal.commentary, "Loved the bridge")

        await modal.on_submit(interaction)

        view.rank_song.assert_awaited_once_with(interaction, song, "Loved the bridge")


@pytest.fixture(name="ranking")
def _ranking_round():
    """A round in its ranking phase with songs from players 102 and 103. Returns (game_id, round_id)."""
    game_id = start_game()
    round_id = get_current_round_db(game_id).round_id
    set_round_theme_db(round_id, "Rain songs")
    upsert_submission_db(round_id, 102, "vid102", "Song by 102")
    upsert_submission_db(round_id, 103, "vid103", "Song by 103")
    close_round_db(round_id)
    return game_id, round_id


def _view(ranking, songs=None, saved=(), channel_id=555):
    game_id, round_id = ranking
    songs = songs or [Submission(round_id, 102, "vid102", "Song by 102"),
                      Submission(round_id, 103, "vid103", "Song by 103")]
    return ListenGameRankingView(songs, list(saved), game_id, round_id, channel_id)


class TestRankingViewSetup:
    """The view shows the control that fits how far the listener has got."""

    async def test_a_fresh_ranking_asks_for_the_last_place_song_first(self, ranking):
        view = _view(ranking)

        assert view.current_rank == 2
        assert isinstance(view.children[0], RankingSelect)
        assert view.children[0].placeholder == "Select your pick for Rank #2..."
        assert [o.label for o in view.children[0].options] == ["Song by 102", "Song by 103"]
        assert len(view.children) == 1               # no Start over yet
        assert view.timeout is None
        embed = view.build_embed()
        assert embed.title == "Listen Game Rankings"
        assert "Select the song you're ranking last" in embed.description

    async def test_saved_picks_from_before_a_restart_are_restored(self, ranking):
        view = _view(ranking, saved=[RankingPick(103, 2, "worst")])

        assert [(r.submission.user_id, r.rank, r.commentary) for r in view.ranked_submissions] == [(103, 2, "worst")]
        assert view.current_rank == 1
        assert [s.user_id for s in view.unranked_submissions] == [102]

    async def test_saved_picks_for_songs_no_longer_in_the_round_are_ignored(self, ranking):
        view = _view(ranking, saved=[RankingPick(999, 2, "ghost")])

        assert view.ranked_submissions == []
        assert view.current_rank == 2

    async def test_one_song_left_is_a_button_not_a_menu(self, ranking):
        view = _view(ranking, saved=[RankingPick(103, 2, "worst")])

        assert isinstance(view.children[0], RankSingleSongButton)
        assert isinstance(view.children[1], StartOverButton)

    async def test_everything_ranked_shows_confirm_and_start_over(self, ranking):
        view = _view(ranking, saved=[RankingPick(103, 2, "worst"), RankingPick(102, 1, "best")])

        assert [type(c) for c in view.children] == [ConfirmRankingButton, StartOverButton]
        assert view.build_embed().description.startswith("✅ **All songs ranked!**")

    async def test_the_embed_shows_the_picks_so_far(self, ranking):
        view = _view(ranking, saved=[RankingPick(103, 2, "worst")])

        embed = view.build_embed()

        assert embed.description == "Here are your rankings so far:"
        assert [(f.name, f.value) for f in embed.fields] == [("#2 - Song by 103", "worst")]


class TestRankingProgress:
    """Each pick is saved as it is made."""

    async def test_picking_a_song_saves_it_and_moves_to_the_next_rank(self, interaction, ranking):
        view = _view(ranking)
        song = view.unranked_submissions[1]

        await view.rank_song(interaction, song, "not my favourite")

        assert get_ranking_picks_db(ranking[1]) == [RankingPick(103, 2, "not my favourite")]
        assert view.current_rank == 1
        assert [s.user_id for s in view.unranked_submissions] == [102]
        [update] = interaction.sent
        assert update.via == "edit" and update.kwargs["view"] is view
        assert update.embed.fields[0].name == "#2 - Song by 103"
        assert isinstance(view.children[0], RankSingleSongButton)

    async def test_the_select_menu_opens_the_commentary_form_for_the_chosen_song(self, interaction, ranking):
        view = _view(ranking)
        select = view.children[0]
        setattr(select, "_values", ["vid103"])

        await select.callback(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, CommentaryModal)
        assert (modal.selected_song.user_id, modal.title) == (103, "2nd Place Commentary")

    async def test_the_single_song_button_opens_the_form_too(self, interaction, ranking):
        view = _view(ranking, saved=[RankingPick(103, 2, "worst")])
        button = view.children[0]

        await button.callback(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        assert (modal.selected_song.user_id, modal.title) == (102, "1st Place Commentary")
        assert button.label == "Rank #1: Song by 102"

    async def test_a_long_title_is_shortened_on_the_button(self):
        button = RankSingleSongButton(_submissions("T" * 200)[0], 1)

        assert len(button.label) <= 80

    async def test_start_over_forgets_every_pick(self, interaction, ranking):
        view = _view(ranking, saved=[RankingPick(103, 2, "worst")])
        save_ranking_pick_db(ranking[1], 103, 2, "worst")

        await view.children[-1].callback(interaction)

        assert get_ranking_picks_db(ranking[1]) == []
        assert view.ranked_submissions == [] and view.current_rank == 2
        assert len(view.unranked_submissions) == 2
        assert isinstance(view.children[0], RankingSelect)
        assert interaction.sent[0].embed.description.startswith("Select the song you're ranking last")

    async def test_a_database_failure_is_reported(self, interaction, ranking, execute):
        execute(Database.LISTEN_GAME, "DROP TABLE listen_round_rankings")
        view = _view(ranking)

        with pytest.raises(Exception) as caught:
            await view.rank_song(interaction, view.unranked_submissions[0], "x")
        await view.on_error(interaction, caught.value, view.children[0])

        assert interaction.sent[0].content == DATABASE_ERROR


class TestConfirmRanking:
    """Confirming saves the results, awards points and starts the reveal."""

    @pytest.fixture(name="started", autouse=True)
    def _reveal(self, monkeypatch):
        started = mock.Mock()
        monkeypatch.setattr("ui.listen_game.start_reveal", started)
        return started

    @staticmethod
    async def _fully_ranked(interaction, ranking, channel):
        interaction.client.get_channel.return_value = channel
        view = _view(ranking)
        await view.rank_song(interaction, view.unranked_submissions[1], "third-ish")    # 103 last (rank 2)
        await view.rank_song(interaction, view.unranked_submissions[0], "best")         # 102 first (rank 1)
        interaction.sent.clear()
        return view

    async def test_saves_the_results_with_points_for_each_rank(self, interaction, ranking, make_channel):
        view = await self._fully_ranked(interaction, ranking, make_channel("listen-game"))

        await view.children[0].callback(interaction)

        assert [(s.user_id, s.rank, s.points_awarded, s.commentary) for s in get_round_results_db(ranking[1])] == \
            [(102, 1, 2, "best"), (103, 2, 1, "third-ish")]
        assert {s.user_id: s.score for s in get_game_leaderboard_db(ranking[0])}[102] == 2
        assert get_round_db(ranking[1]).status is RoundStatus.REVEALING

    async def test_tells_the_listener_and_starts_the_reveal_in_the_game_channel(self, interaction, ranking,
                                                                                make_channel, started):
        channel = make_channel("listen-game")
        view = await self._fully_ranked(interaction, ranking, channel)

        await view.children[0].callback(interaction)

        [reply] = interaction.sent
        assert (reply.via, reply.content, reply.ephemeral) == (
            "followup", "✅ Results locked in! The reveal is starting in the game channel.", True)
        interaction.response.defer.assert_awaited()
        started.assert_called_once_with(channel, ranking[1])

    async def test_a_second_press_is_ignored(self, interaction, ranking, make_channel, started):
        view = await self._fully_ranked(interaction, ranking, make_channel("listen-game"))
        button = view.children[0]
        await button.callback(interaction)
        interaction.sent.clear()

        await button.callback(interaction)

        assert interaction.sent[0].content == "Results are already being published for this round."
        assert interaction.sent[0].ephemeral
        assert started.call_count == 1

    async def test_results_that_were_already_saved_are_not_saved_twice(
            self, interaction, ranking, make_channel, started):
        view = await self._fully_ranked(interaction, ranking, make_channel("listen-game"))
        await view.children[0].callback(interaction)
        interaction.sent.clear()
        second_view = _view(ranking)                      # e.g. the command was run again after a restart
        second_view.ranked_submissions = view.ranked_submissions
        second_view.unranked_submissions = []
        second_view.setup_select_menu()

        await second_view.children[0].callback(interaction)

        assert interaction.sent[0].content.startswith("ℹ️ The results for this round were already saved")
        assert {s.user_id: s.score for s in get_game_leaderboard_db(ranking[0])}[102] == 2     # not doubled
        assert started.call_count == 2                # still makes sure the reveal is running

    async def test_a_failed_save_can_be_retried(self, interaction, ranking, make_channel, execute):
        view = await self._fully_ranked(interaction, ranking, make_channel("listen-game"))
        button = view.children[0]
        execute(Database.LISTEN_GAME, "ALTER TABLE listen_submissions RENAME TO listen_submissions_away")

        with pytest.raises(sqlite3.OperationalError):
            await button.callback(interaction)
        assert view.results_confirmed is False

        execute(Database.LISTEN_GAME, "ALTER TABLE listen_submissions_away RENAME TO listen_submissions")
        await button.callback(interaction)
        assert get_round_db(ranking[1]).status is RoundStatus.REVEALING

    async def test_a_missing_channel_is_logged_and_the_results_are_still_saved(
            self, interaction, ranking, caplog, started):
        view = await self._fully_ranked(interaction, ranking, None)

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await view.children[0].callback(interaction)

        assert "Could not find channel 555 to reveal round" in caplog.text
        started.assert_not_called()
        assert get_round_db(ranking[1]).status is RoundStatus.REVEALING
