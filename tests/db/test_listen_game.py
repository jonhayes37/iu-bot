"""Tests for db/listen_game.py: the Listen Game's games, rounds, submissions and rankings.

A game is registration -> playing -> finished. A round is
setting_theme -> submitting -> ranking -> revealing -> completed (or skipped by the GM).
"""

import random
import sqlite3
import threading

import pytest

from config import Database
from db.errors import InvalidStateError
from db.listen_game import (
    Game, GameStatus, PendingPlayer, RankingPick, Round, RoundResult, RoundStatus, SaveResult, Standing, Submission,
    SwapOutcome, advance_game_turn_db, clear_ranking_picks_db, close_round_db, create_game_db, delete_submission_db,
    get_active_gm_id, get_current_round_db, get_expired_rounds_db, get_game_by_status_db, get_game_leaderboard_db,
    get_game_rounds_db, get_missing_players_for_reminders_db, get_next_host_id_db, get_ordered_players_db,
    get_ranking_picks_db, get_registered_players_db, get_revealing_round_ids_db, get_round_db, get_round_results_db,
    get_round_submissions_db, get_user_submission_db, is_round_complete_db, is_video_claimed_by_other_db,
    register_player_db, remove_player_from_game_db, save_ranking_pick_db, save_round_results_db,
    set_reveal_step_db, set_round_theme_db, skip_game_turn_db, start_game_db, swap_player_orders_db,
    unregister_player_db, update_game_start_message_db, update_last_reminded_db, update_round_playlist_db,
    update_round_ruleset_message_db, update_round_status_message_db, upsert_submission_db
)

GM, SUB_GM = 1, 2
DEFAULT_PLAYERS = (101, 102, 103)
PLAYERS = list(DEFAULT_PLAYERS)


@pytest.fixture(autouse=True)
def _listen_game_database(databases):
    databases(Database.LISTEN_GAME)


@pytest.fixture(autouse=True)
def in_registration_order(monkeypatch):
    """
    Makes start_game_db keep the players in the order they joined instead of shuffling them, so the first
    player hosts round 1. Tests of the shuffle itself replace `random.shuffle` again.
    """
    monkeypatch.setattr(random, "shuffle", lambda players: None)


def _registering(players=DEFAULT_PLAYERS, max_round_days=None):
    game_id = create_game_db(GM, SUB_GM, max_round_days)
    for user_id in players:
        register_player_db(game_id, user_id)
    return game_id


def _playing(players=DEFAULT_PLAYERS, max_round_days=None):
    """A started game. Turn order is the order given, so the first player hosts round 1."""
    game_id = _registering(players, max_round_days)
    assert start_game_db(game_id) is not None
    return game_id


def _round(game_id):
    return get_current_round_db(game_id)


def _submitting(players=DEFAULT_PLAYERS, max_round_days=None):
    """A started game whose current round has its theme and is taking submissions."""
    game_id = _playing(players, max_round_days)
    current = _round(game_id)
    set_round_theme_db(current.round_id, "Ballads")
    return game_id, current.round_id


def _ranking(players=DEFAULT_PLAYERS):
    """A game whose round has a song from every non-host player and has been closed for ranking."""
    game_id, round_id = _submitting(players)
    for user_id in players[1:]:
        upsert_submission_db(round_id, user_id, f"vid{user_id}", f"Song {user_id}")
    assert close_round_db(round_id)
    return game_id, round_id


def _results(players=DEFAULT_PLAYERS):
    """A full ranking of the non-host players: the last player is 1st."""
    submitters = list(reversed(players[1:]))
    return [RoundResult(user_id, rank, 10 - rank, f"note {rank}") for rank, user_id in enumerate(submitters, start=1)]


def _revealing(players=DEFAULT_PLAYERS):
    game_id, round_id = _ranking(players)
    assert save_round_results_db(game_id, round_id, _results(players)) is SaveResult.SAVED
    return game_id, round_id


class TestCreateGame:
    """Only one game can be running at a time."""

    def test_a_new_game_starts_in_registration(self):
        game_id = create_game_db(GM, SUB_GM, 3)

        game = get_game_by_status_db(GameStatus.REGISTRATION)
        assert (game.game_id, game.gm_id, game.sub_gm_id, game.status, game.max_round_days) == \
            (game_id, GM, SUB_GM, GameStatus.REGISTRATION, 3)
        assert game.game_start_message_id is None

    def test_the_round_deadline_is_optional(self):
        create_game_db(GM, SUB_GM, None)

        assert get_game_by_status_db(GameStatus.REGISTRATION).max_round_days is None

    def test_a_second_game_is_refused_while_one_is_in_registration(self):
        create_game_db(GM, SUB_GM, None)

        assert create_game_db(GM, SUB_GM, None) is None

    def test_a_second_game_is_refused_while_one_is_being_played(self):
        _playing()

        assert create_game_db(GM, SUB_GM, None) is None

    def test_a_new_game_is_allowed_after_the_last_one_finished(self, execute):
        first = _playing()
        execute(Database.LISTEN_GAME, "UPDATE listen_games SET status = 'finished'")

        second = create_game_db(GM, SUB_GM, None)

        assert second is not None and second != first

    def test_two_people_creating_at_once_get_only_one_game(self, query):
        gate = threading.Barrier(2)
        results = []

        def create():
            gate.wait()
            results.append(create_game_db(GM, SUB_GM, None))

        threads = [threading.Thread(target=create) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len([r for r in results if r is not None]) == 1
        assert len(query(Database.LISTEN_GAME, "SELECT * FROM listen_games")) == 1

    def test_no_game_in_a_status_is_none(self):
        assert get_game_by_status_db(GameStatus.PLAYING) is None


class TestRegistration:
    """Players join and leave while the game is in registration."""

    def test_joining_adds_the_player_once(self):
        game_id = create_game_db(GM, SUB_GM, None)

        assert register_player_db(game_id, 101) is True
        assert register_player_db(game_id, 101) is False

        assert get_registered_players_db(game_id) == [101]

    def test_leaving_removes_them(self):
        game_id = _registering()

        assert unregister_player_db(game_id, 102) is True

        assert sorted(get_registered_players_db(game_id)) == [101, 103]

    def test_leaving_when_not_registered_is_false(self):
        game_id = _registering()

        assert unregister_player_db(game_id, 999) is False

    def test_a_new_player_starts_with_no_score(self):
        game_id = _registering([101])

        assert get_game_leaderboard_db(game_id) == [Standing(101, 0)]

    def test_players_belong_to_their_own_game(self, execute):
        first = _registering([101])
        execute(Database.LISTEN_GAME, "UPDATE listen_games SET status = 'finished'")
        second = create_game_db(GM, SUB_GM, None)
        register_player_db(second, 202)

        assert get_registered_players_db(first) == [101]
        assert get_registered_players_db(second) == [202]

    def test_removing_a_player_from_a_game(self):
        game_id = _playing()

        assert remove_player_from_game_db(game_id, 103) is True
        assert remove_player_from_game_db(game_id, 103) is False

        assert get_ordered_players_db(game_id) == [101, 102]


class TestStartGame:
    """Starting shuffles the turn order and opens round 1 for the first player."""

    def test_returns_the_turn_order_and_opens_round_one_for_the_first_host(self):
        game_id = _registering()

        order = start_game_db(game_id)

        assert order == PLAYERS
        assert get_ordered_players_db(game_id) == PLAYERS
        current = _round(game_id)
        assert (current.host_id, current.status, current.game_id) == (101, RoundStatus.SETTING_THEME, game_id)
        assert get_game_by_status_db(GameStatus.PLAYING).game_id == game_id
        assert get_game_by_status_db(GameStatus.REGISTRATION) is None

    def test_the_order_is_shuffled(self, monkeypatch):
        game_id = _registering()
        monkeypatch.setattr(random, "shuffle", lambda players: players.reverse())

        assert start_game_db(game_id) == [103, 102, 101]
        assert _round(game_id).host_id == 103

    def test_every_player_gets_a_distinct_turn_number(self, query):
        game_id = _registering([101, 102, 103, 104, 105])
        start_game_db(game_id)

        orders = [r["turn_order"] for r in query(Database.LISTEN_GAME, "SELECT turn_order FROM listen_players")]

        assert sorted(orders) == [0, 1, 2, 3, 4]

    @pytest.mark.parametrize("players", [[], [101]])
    def test_fewer_than_two_players_cannot_start(self, players):
        game_id = _registering(players)

        assert start_game_db(game_id) is None

        assert get_game_by_status_db(GameStatus.REGISTRATION).game_id == game_id
        assert get_current_round_db(game_id) is None

    def test_two_players_is_enough(self):
        assert start_game_db(_registering([101, 102])) is not None

    def test_a_game_that_has_started_cannot_be_started_again(self, query):
        game_id = _playing()

        assert start_game_db(game_id) is None

        assert len(query(Database.LISTEN_GAME, "SELECT * FROM listen_rounds")) == 1

    def test_an_unknown_game_cannot_be_started(self):
        assert start_game_db(999) is None

    def test_the_start_message_can_be_saved(self):
        game_id = _registering()

        update_game_start_message_db(game_id, 5551)

        assert get_game_by_status_db(GameStatus.REGISTRATION).game_start_message_id == 5551


class TestLeaderboardAndOrder:
    """Reading the standings and the running order."""

    def test_the_leaderboard_is_highest_score_first(self, execute):
        game_id = _playing()
        for user_id, score in [(101, 5), (102, 30), (103, 12)]:
            execute(Database.LISTEN_GAME, "UPDATE listen_players SET score = ? WHERE user_id = ?", score, user_id)

        assert get_game_leaderboard_db(game_id) == [Standing(102, 30), Standing(103, 12), Standing(101, 5)]

    def test_a_game_with_no_players_has_an_empty_leaderboard(self):
        assert get_game_leaderboard_db(999) == []

    def test_ordered_players_follow_the_turn_order(self, monkeypatch):
        game_id = _registering()
        monkeypatch.setattr(random, "shuffle", lambda players: players.reverse())
        start_game_db(game_id)

        assert get_ordered_players_db(game_id) == [103, 102, 101]


class TestActiveGm:
    """The substitute GM runs a round when the main GM is the listener."""

    GAME = Game(game_id=1, gm_id=GM, sub_gm_id=SUB_GM, status=GameStatus.PLAYING)

    def test_the_main_gm_normally_runs_the_round(self):
        listener_round = Round(round_id=1, game_id=1, host_id=101, status=RoundStatus.SUBMITTING)

        assert get_active_gm_id(self.GAME, listener_round) == GM

    def test_the_substitute_runs_it_when_the_gm_is_the_listener(self):
        listener_round = Round(round_id=1, game_id=1, host_id=GM, status=RoundStatus.SUBMITTING)

        assert get_active_gm_id(self.GAME, listener_round) == SUB_GM

    def test_with_no_round_it_is_the_main_gm(self):
        assert get_active_gm_id(self.GAME) == GM


class TestSwapPlayerOrders:
    """The GM can swap two players who haven't had their turn yet."""

    def test_swaps_two_players_after_the_host(self):
        game_id = _playing()

        assert swap_player_orders_db(game_id, 102, 103) is SwapOutcome.SWAPPED

        assert get_ordered_players_db(game_id) == [101, 103, 102]

    def test_the_current_host_cannot_be_swapped(self):
        game_id = _playing()

        assert swap_player_orders_db(game_id, 101, 102) is SwapOutcome.NOT_AFTER_HOST
        assert swap_player_orders_db(game_id, 102, 101) is SwapOutcome.NOT_AFTER_HOST

        assert get_ordered_players_db(game_id) == PLAYERS

    def test_someone_who_has_already_had_a_turn_cannot_be_swapped(self):
        game_id = _playing()
        skip_game_turn_db(game_id, _round(game_id).round_id)   # 102 is now hosting

        assert swap_player_orders_db(game_id, 101, 103) is SwapOutcome.NOT_AFTER_HOST

    def test_a_player_who_is_not_in_the_game(self):
        game_id = _playing()

        assert swap_player_orders_db(game_id, 102, 999) is SwapOutcome.PLAYER_NOT_IN_GAME
        assert swap_player_orders_db(game_id, 999, 102) is SwapOutcome.PLAYER_NOT_IN_GAME

    def test_with_no_round_in_play_there_is_no_host(self):
        game_id = _registering()

        assert swap_player_orders_db(game_id, 102, 103) is SwapOutcome.NO_ACTIVE_HOST

    def test_swapping_changes_who_hosts_next(self):
        game_id = _playing()
        swap_player_orders_db(game_id, 102, 103)

        assert skip_game_turn_db(game_id, _round(game_id).round_id) == 103


class TestRoundLifecycle:
    """Setting the theme, taking submissions, and closing for ranking."""

    def test_a_new_round_is_waiting_for_its_theme(self):
        game_id = _playing()

        current = _round(game_id)

        assert (current.status, current.theme, current.playlist_id, current.reveal_step) == \
            (RoundStatus.SETTING_THEME, None, None, 0)

    def test_setting_the_theme_opens_submissions_and_starts_the_clock(self, execute):
        game_id = _playing()
        current = _round(game_id)
        execute(Database.LISTEN_GAME, "UPDATE listen_rounds SET started_at = '2020-01-01 00:00:00'")

        assert set_round_theme_db(current.round_id, "Ballads") is True

        updated = _round(game_id)
        assert (updated.theme, updated.status) == ("Ballads", RoundStatus.SUBMITTING)
        assert updated.started_at != "2020-01-01 00:00:00"

    def test_the_host_can_change_the_ruleset_while_submissions_are_open(self):
        _, round_id = _submitting()

        assert set_round_theme_db(round_id, "New theme") is True

        assert get_round_db(round_id).theme == "New theme"
        assert get_round_db(round_id).status is RoundStatus.SUBMITTING

    def test_the_theme_cannot_change_once_the_round_is_past_submitting(self):
        _, round_id = _ranking()

        assert set_round_theme_db(round_id, "Too late") is False

        assert get_round_db(round_id).theme == "Ballads"

    def test_the_theme_of_an_unknown_round_is_false(self):
        assert set_round_theme_db(999, "x") is False

    def test_closing_moves_a_submitting_round_to_ranking(self):
        _, round_id = _submitting()

        assert close_round_db(round_id) is True

        assert get_round_db(round_id).status is RoundStatus.RANKING

    def test_closing_twice_only_works_once(self):
        _, round_id = _submitting()
        close_round_db(round_id)

        assert close_round_db(round_id) is False

    def test_a_round_still_waiting_for_its_theme_cannot_be_closed(self):
        game_id = _playing()

        assert close_round_db(_round(game_id).round_id) is False

    def test_message_and_playlist_ids_are_saved_on_the_round(self):
        _, round_id = _submitting()

        update_round_playlist_db(round_id, "PLabc")
        update_round_status_message_db(round_id, 7001)
        update_round_ruleset_message_db(round_id, 7002)

        saved = get_round_db(round_id)
        assert (saved.playlist_id, saved.status_message_id, saved.ruleset_message_id) == ("PLabc", 7001, 7002)

    def test_the_current_round_is_the_latest_one_in_play(self):
        game_id = _playing()
        first = _round(game_id)
        skip_game_turn_db(game_id, first.round_id)

        assert _round(game_id).round_id != first.round_id
        assert _round(game_id).host_id == 102

    def test_a_game_with_no_rounds_in_play_has_no_current_round(self):
        game_id = _registering()

        assert get_current_round_db(game_id) is None

    def test_a_finished_round_is_not_current(self):
        game_id, round_id = _revealing()
        advance_game_turn_db(game_id, round_id)

        assert _round(game_id).round_id != round_id

    def test_all_rounds_of_a_game_come_back_oldest_first(self):
        game_id = _playing()
        skip_game_turn_db(game_id, _round(game_id).round_id)

        rounds = get_game_rounds_db(game_id)

        assert [r.host_id for r in rounds] == [101, 102]
        assert [r.status for r in rounds] == [RoundStatus.SKIPPED, RoundStatus.SETTING_THEME]

    def test_an_unknown_round_is_none(self):
        assert get_round_db(999) is None


class TestRoundCompletion:
    """A round is complete when every player except the host has sent a song."""

    def test_incomplete_until_everyone_but_the_host_has_submitted(self):
        game_id, round_id = _submitting()

        assert is_round_complete_db(game_id, round_id) is False
        upsert_submission_db(round_id, 102, "v1", "t1")
        assert is_round_complete_db(game_id, round_id) is False
        upsert_submission_db(round_id, 103, "v2", "t2")
        assert is_round_complete_db(game_id, round_id) is True

    def test_resubmitting_does_not_count_twice(self):
        game_id, round_id = _submitting()
        upsert_submission_db(round_id, 102, "v1", "t1")
        upsert_submission_db(round_id, 102, "v2", "t2")

        assert is_round_complete_db(game_id, round_id) is False

    def test_a_two_player_round_is_complete_after_one_song(self):
        game_id, round_id = _submitting([101, 102])

        upsert_submission_db(round_id, 102, "v1", "t1")

        assert is_round_complete_db(game_id, round_id) is True


class TestDeadlines:
    """Rounds with a deadline expire max_round_days after their theme was set."""

    def _set_started(self, execute, round_id, started_at):
        execute(Database.LISTEN_GAME, "UPDATE listen_rounds SET started_at = ? WHERE round_id = ?",
                started_at, round_id)

    def test_a_round_expires_after_its_number_of_days(self, execute, frozen_time):
        _, round_id = _submitting(max_round_days=3)
        self._set_started(execute, round_id, "2026-03-01 12:00:00")

        frozen_time("2026-03-04 11:59:59")
        assert get_expired_rounds_db() == []

        frozen_time("2026-03-04 12:00:00")
        assert [r.round_id for r in get_expired_rounds_db()] == [round_id]

    def test_a_game_without_a_deadline_never_expires(self, execute, frozen_time):
        _, round_id = _submitting(max_round_days=None)
        self._set_started(execute, round_id, "2020-01-01 00:00:00")
        frozen_time("2030-01-01 00:00:00")

        assert get_expired_rounds_db() == []

    def test_only_rounds_taking_submissions_can_expire(self, execute, frozen_time):
        game_id = _playing(max_round_days=1)
        waiting = _round(game_id)
        self._set_started(execute, waiting.round_id, "2020-01-01 00:00:00")
        frozen_time("2030-01-01 00:00:00")

        assert get_expired_rounds_db() == []

    def test_an_expired_round_is_returned_as_a_round(self, execute, frozen_time):
        _, round_id = _submitting(max_round_days=1)
        self._set_started(execute, round_id, "2026-03-01 00:00:00")
        frozen_time("2026-03-05 00:00:00")

        [expired] = get_expired_rounds_db()

        assert isinstance(expired, Round)
        assert (expired.status, expired.theme) == (RoundStatus.SUBMITTING, "Ballads")


class TestReminders:
    """Players who haven't submitted are reminded."""

    def test_lists_players_still_to_submit_but_not_the_host(self):
        game_id, round_id = _submitting(max_round_days=5)
        update_round_ruleset_message_db(round_id, 777)

        missing = get_missing_players_for_reminders_db()

        assert sorted(p.user_id for p in missing) == [102, 103]
        first = missing[0]
        assert isinstance(first, PendingPlayer)
        assert (first.game_id, first.round_id, first.ruleset_message_id, first.max_round_days, first.last_reminded_at) \
            == (game_id, round_id, 777, 5, None)
        assert first.started_at

    def test_players_who_have_submitted_are_left_out(self):
        _, round_id = _submitting()
        upsert_submission_db(round_id, 102, "v1", "t1")

        assert [p.user_id for p in get_missing_players_for_reminders_db()] == [103]

    def test_nobody_is_reminded_before_the_theme_is_set_or_after_submissions_close(self):
        game_id = _playing()
        assert get_missing_players_for_reminders_db() == []

        set_round_theme_db(_round(game_id).round_id, "Ballads")
        close_round_db(_round(game_id).round_id)
        assert get_missing_players_for_reminders_db() == []

    def test_a_reminder_is_timestamped(self):
        game_id, _ = _submitting()

        update_last_reminded_db(game_id, 102)

        reminded = {p.user_id: p.last_reminded_at for p in get_missing_players_for_reminders_db()}
        assert reminded[102] is not None and reminded[103] is None


class TestSubmissions:
    """One song per player per round, which they can change until the round closes."""

    def test_a_submission_is_stored(self):
        _, round_id = _submitting()

        upsert_submission_db(round_id, 102, "vid1", "IU - Good Day")

        submission = get_user_submission_db(round_id, 102)
        assert isinstance(submission, Submission)
        assert (submission.video_id, submission.raw_title, submission.rank, submission.points_awarded,
                submission.commentary) == ("vid1", "IU - Good Day", None, 0, None)

    def test_submitting_again_replaces_the_song(self):
        _, round_id = _submitting()
        upsert_submission_db(round_id, 102, "vid1", "first")

        upsert_submission_db(round_id, 102, "vid2", "second")

        assert [s.video_id for s in get_round_submissions_db(round_id)] == ["vid2"]

    def test_a_missing_submission_is_none(self):
        _, round_id = _submitting()

        assert get_user_submission_db(round_id, 102) is None

    def test_all_the_rounds_submissions_come_back(self):
        _, round_id = _submitting()
        upsert_submission_db(round_id, 102, "v1", "t1")
        upsert_submission_db(round_id, 103, "v2", "t2")

        assert sorted(s.user_id for s in get_round_submissions_db(round_id)) == [102, 103]

    def test_deleting_a_submission(self):
        _, round_id = _submitting()
        upsert_submission_db(round_id, 102, "v1", "t1")

        assert delete_submission_db(round_id, 102) is True
        assert delete_submission_db(round_id, 102) is False

        assert get_user_submission_db(round_id, 102) is None

    def test_a_song_already_sent_by_someone_else_is_claimed(self):
        _, round_id = _submitting()
        upsert_submission_db(round_id, 102, "same", "t")

        assert is_video_claimed_by_other_db(round_id, 103, "same") is True

    def test_a_players_own_song_is_not_claimed_against_them(self):
        _, round_id = _submitting()
        upsert_submission_db(round_id, 102, "same", "t")

        assert is_video_claimed_by_other_db(round_id, 102, "same") is False

    def test_the_same_song_may_be_used_in_another_round(self):
        game_id, round_id = _submitting()
        upsert_submission_db(round_id, 102, "same", "t")
        skip_game_turn_db(game_id, round_id)
        next_round = _round(game_id).round_id

        assert is_video_claimed_by_other_db(next_round, 103, "same") is False

    def test_a_song_nobody_sent_is_free(self):
        _, round_id = _submitting()

        assert is_video_claimed_by_other_db(round_id, 102, "new") is False


class TestRankingPicks:
    """The listener's picks are saved as they go, so a restart doesn't lose them."""

    @pytest.fixture
    def ranking(self):
        return _ranking()

    def test_no_picks_yet(self, ranking):
        assert get_ranking_picks_db(ranking[1]) == []

    def test_picks_come_back_last_place_first(self, ranking):
        _, round_id = ranking
        save_ranking_pick_db(round_id, 102, 1, "best")
        save_ranking_pick_db(round_id, 103, 2, "worst")

        assert get_ranking_picks_db(round_id) == [RankingPick(103, 2, "worst"), RankingPick(102, 1, "best")]

    def test_picking_a_song_again_replaces_its_pick(self, ranking):
        _, round_id = ranking
        save_ranking_pick_db(round_id, 102, 1, "first thought")

        save_ranking_pick_db(round_id, 102, 2, "second thought")

        assert get_ranking_picks_db(round_id) == [RankingPick(102, 2, "second thought")]

    def test_clearing_lets_them_start_again(self, ranking):
        _, round_id = ranking
        save_ranking_pick_db(round_id, 102, 1, "x")

        clear_ranking_picks_db(round_id)

        assert get_ranking_picks_db(round_id) == []

    def test_clearing_only_affects_that_round(self):
        _, round_id = _ranking()
        save_ranking_pick_db(round_id, 102, 1, "x")

        clear_ranking_picks_db(round_id + 100)

        assert len(get_ranking_picks_db(round_id)) == 1

    def test_a_pick_needs_a_song_to_belong_to(self, ranking):
        _, round_id = ranking

        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            save_ranking_pick_db(round_id, 999, 1, "no such submission")

    def test_deleting_a_song_removes_its_pick(self, ranking):
        _, round_id = ranking
        save_ranking_pick_db(round_id, 102, 1, "x")

        delete_submission_db(round_id, 102)

        assert get_ranking_picks_db(round_id) == []


class TestSaveRoundResults:
    """Confirming rankings saves them, awards the points and starts the reveal, exactly once."""

    def test_saves_ranks_commentary_and_points_and_starts_the_reveal(self):
        game_id, round_id = _ranking()

        outcome = save_round_results_db(game_id, round_id, _results())

        assert outcome is SaveResult.SAVED
        assert get_round_db(round_id).status is RoundStatus.REVEALING
        assert [(s.user_id, s.rank, s.points_awarded, s.commentary) for s in get_round_results_db(round_id)] == \
            [(103, 1, 9, "note 1"), (102, 2, 8, "note 2")]

    def test_points_are_added_to_the_players_scores(self):
        game_id, round_id = _ranking()

        save_round_results_db(game_id, round_id, _results())

        assert {s.user_id: s.score for s in get_game_leaderboard_db(game_id)} == {101: 0, 102: 8, 103: 9}

    def test_scores_add_up_across_rounds(self):
        game_id, round_id = _revealing()
        advance_game_turn_db(game_id, round_id)
        second = _round(game_id)
        set_round_theme_db(second.round_id, "Debuts")
        for user_id in (101, 103):
            upsert_submission_db(second.round_id, user_id, f"w{user_id}", "t")
        close_round_db(second.round_id)

        save_round_results_db(game_id, second.round_id, [RoundResult(103, 1, 10, "a"), RoundResult(101, 2, 5, "b")])

        assert {s.user_id: s.score for s in get_game_leaderboard_db(game_id)} == {101: 5, 102: 8, 103: 19}

    def test_confirming_twice_does_not_award_the_points_twice(self):
        game_id, round_id = _ranking()
        save_round_results_db(game_id, round_id, _results())

        again = save_round_results_db(game_id, round_id, _results())

        assert again is SaveResult.NOT_IN_RANKING
        assert {s.user_id: s.score for s in get_game_leaderboard_db(game_id)} == {101: 0, 102: 8, 103: 9}

    def test_two_confirmations_at_once_award_the_points_once(self):
        game_id, round_id = _ranking()
        gate = threading.Barrier(2)
        outcomes = []

        def confirm():
            gate.wait()
            outcomes.append(save_round_results_db(game_id, round_id, _results()))

        threads = [threading.Thread(target=confirm) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(o.value for o in outcomes) == ["not_in_ranking", "saved"]
        assert {s.user_id: s.score for s in get_game_leaderboard_db(game_id)} == {101: 0, 102: 8, 103: 9}

    @pytest.mark.parametrize("prepare", ["submitting", "setting_theme"])
    def test_a_round_that_is_not_in_ranking_is_refused_and_unchanged(self, prepare):
        if prepare == "submitting":
            game_id, round_id = _submitting()
        else:
            game_id = _playing()
            round_id = _round(game_id).round_id

        assert save_round_results_db(game_id, round_id, _results()) is SaveResult.NOT_IN_RANKING

        assert {s.user_id: s.score for s in get_game_leaderboard_db(game_id)} == {101: 0, 102: 0, 103: 0}

    def test_the_saved_picks_are_cleared_when_confirmed(self):
        game_id, round_id = _ranking()
        save_ranking_pick_db(round_id, 102, 2, "x")

        save_round_results_db(game_id, round_id, _results())

        assert get_ranking_picks_db(round_id) == []

    def test_the_reveal_starts_from_the_beginning(self, execute):
        game_id, round_id = _ranking()
        execute(Database.LISTEN_GAME, "UPDATE listen_rounds SET reveal_step = 4 WHERE round_id = ?", round_id)

        save_round_results_db(game_id, round_id, _results())

        assert get_round_db(round_id).reveal_step == 0

    def test_results_are_best_rank_first_and_skip_unranked_songs(self):
        game_id, round_id = _ranking()
        save_round_results_db(game_id, round_id, [RoundResult(103, 1, 9, "only")])

        assert [s.user_id for s in get_round_results_db(round_id)] == [103]


class TestReveal:
    """The reveal is posted step by step and can resume after a restart."""

    def test_a_round_being_revealed_is_listed(self):
        _, round_id = _revealing()

        assert get_revealing_round_ids_db() == [round_id]

    def test_other_rounds_are_not_listed(self):
        _ranking()

        assert get_revealing_round_ids_db() == []

    def test_progress_is_remembered(self):
        _, round_id = _revealing()

        set_reveal_step_db(round_id, 3)

        assert get_round_db(round_id).reveal_step == 3

    def test_the_round_being_revealed_is_still_the_current_round(self):
        game_id, round_id = _revealing()

        assert _round(game_id).round_id == round_id


class TestAdvanceGameTurn:
    """After the reveal the round is completed and the next player's round begins."""

    def test_completes_the_round_and_opens_the_next_players(self):
        game_id, round_id = _revealing()

        assert advance_game_turn_db(game_id, round_id) is True

        assert get_round_db(round_id).status is RoundStatus.COMPLETED
        assert (_round(game_id).host_id, _round(game_id).status) == (102, RoundStatus.SETTING_THEME)

    def test_the_last_turn_finishes_the_game(self):
        game_id = _playing([101, 102])
        current = _round(game_id)
        set_round_theme_db(current.round_id, "t")
        upsert_submission_db(current.round_id, 102, "v", "t")
        close_round_db(current.round_id)
        save_round_results_db(game_id, current.round_id, [RoundResult(102, 1, 5, "x")])
        advance_game_turn_db(game_id, current.round_id)         # 102 hosts next
        second = _round(game_id)
        set_round_theme_db(second.round_id, "t")
        upsert_submission_db(second.round_id, 101, "w", "t")
        close_round_db(second.round_id)
        save_round_results_db(game_id, second.round_id, [RoundResult(101, 1, 5, "x")])

        assert advance_game_turn_db(game_id, second.round_id) is True

        assert get_game_by_status_db(GameStatus.FINISHED).game_id == game_id
        assert get_current_round_db(game_id) is None

    def test_calling_it_again_after_it_worked_is_harmless(self, query):
        game_id, round_id = _revealing()
        advance_game_turn_db(game_id, round_id)

        assert advance_game_turn_db(game_id, round_id) is True

        assert len(query(Database.LISTEN_GAME, "SELECT * FROM listen_rounds")) == 2

    def test_a_round_that_is_not_being_revealed_is_not_advanced(self, query):
        game_id, round_id = _ranking()

        assert advance_game_turn_db(game_id, round_id) is False

        assert get_round_db(round_id).status is RoundStatus.RANKING
        assert len(query(Database.LISTEN_GAME, "SELECT * FROM listen_rounds")) == 1

    def test_an_unknown_round_is_not_advanced(self):
        assert advance_game_turn_db(1, 999) is False

    def test_two_calls_at_once_open_only_one_new_round(self, query):
        game_id, round_id = _revealing()
        gate = threading.Barrier(2)

        def advance():
            gate.wait()
            advance_game_turn_db(game_id, round_id)

        threads = [threading.Thread(target=advance) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(query(Database.LISTEN_GAME, "SELECT * FROM listen_rounds")) == 2


class TestNextHost:
    """get_next_host_id_db looks ahead without changing anything."""

    def test_names_the_next_player(self):
        game_id = _playing()

        assert get_next_host_id_db(game_id, _round(game_id).round_id) == 102

    def test_does_not_start_a_round(self, query):
        game_id = _playing()

        get_next_host_id_db(game_id, _round(game_id).round_id)

        assert len(query(Database.LISTEN_GAME, "SELECT * FROM listen_rounds")) == 1

    def test_the_last_players_turn_has_no_next_host(self):
        game_id = _playing([101, 102])
        skip_game_turn_db(game_id, _round(game_id).round_id)

        assert get_next_host_id_db(game_id, _round(game_id).round_id) is None

    def test_a_host_who_left_the_game_is_reported_not_treated_as_the_end(self):
        game_id = _playing()
        round_id = _round(game_id).round_id
        remove_player_from_game_db(game_id, _round(game_id).host_id)

        with pytest.raises(InvalidStateError):
            get_next_host_id_db(game_id, round_id)


class TestSkipGameTurn:
    """The GM can skip a round that hasn't reached its reveal."""

    @pytest.mark.parametrize("stage", ["setting_theme", "submitting", "ranking"])
    def test_a_round_before_the_reveal_can_be_skipped(self, stage):
        game_id = _playing()
        round_id = _round(game_id).round_id
        if stage != "setting_theme":
            set_round_theme_db(round_id, "t")
        if stage == "ranking":
            close_round_db(round_id)

        assert skip_game_turn_db(game_id, round_id) == 102

        assert get_round_db(round_id).status is RoundStatus.SKIPPED
        assert (_round(game_id).host_id, _round(game_id).status) == (102, RoundStatus.SETTING_THEME)

    def test_skipping_the_last_turn_ends_the_game_and_returns_none(self):
        game_id = _playing([101, 102])
        skip_game_turn_db(game_id, _round(game_id).round_id)

        assert skip_game_turn_db(game_id, _round(game_id).round_id) is None

        assert get_game_by_status_db(GameStatus.FINISHED).game_id == game_id

    def test_a_round_that_is_being_revealed_cannot_be_skipped(self):
        game_id, round_id = _revealing()

        with pytest.raises(InvalidStateError):
            skip_game_turn_db(game_id, round_id)

        assert get_round_db(round_id).status is RoundStatus.REVEALING

    def test_a_finished_round_cannot_be_skipped(self):
        game_id, round_id = _revealing()
        advance_game_turn_db(game_id, round_id)

        with pytest.raises(InvalidStateError):
            skip_game_turn_db(game_id, round_id)

    def test_skipping_twice_is_refused_and_starts_no_extra_round(self, query):
        game_id = _playing()
        round_id = _round(game_id).round_id
        skip_game_turn_db(game_id, round_id)

        with pytest.raises(InvalidStateError):
            skip_game_turn_db(game_id, round_id)

        assert len(query(Database.LISTEN_GAME, "SELECT * FROM listen_rounds")) == 2

    def test_an_unknown_round_cannot_be_skipped(self):
        with pytest.raises(InvalidStateError):
            skip_game_turn_db(1, 999)

    def test_skipped_rounds_award_no_points(self):
        game_id, round_id = _ranking()
        skip_game_turn_db(game_id, round_id)

        assert {s.score for s in get_game_leaderboard_db(game_id)} == {0}


class TestWholeGame:
    """A game played from registration to the final leaderboard."""

    def test_three_players_each_host_once_and_the_game_ends(self):
        game_id = _playing()
        hosts = []

        for _ in PLAYERS:
            current = _round(game_id)
            hosts.append(current.host_id)
            set_round_theme_db(current.round_id, "Theme")
            guests = [p for p in PLAYERS if p != current.host_id]
            for guest in guests:
                upsert_submission_db(current.round_id, guest, f"{current.round_id}-{guest}", "t")
            assert is_round_complete_db(game_id, current.round_id)
            close_round_db(current.round_id)
            save_round_results_db(game_id, current.round_id,
                                  [RoundResult(guest, rank, 10 - rank, "c") for rank, guest in enumerate(guests, 1)])
            advance_game_turn_db(game_id, current.round_id)

        assert hosts == PLAYERS
        assert get_game_by_status_db(GameStatus.FINISHED).game_id == game_id
        assert get_current_round_db(game_id) is None
        assert sum(s.score for s in get_game_leaderboard_db(game_id)) == 3 * (9 + 8)
        assert all(r.status is RoundStatus.COMPLETED for r in get_game_rounds_db(game_id))
