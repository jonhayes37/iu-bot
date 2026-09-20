"""Tests for db/tournaments.py: brackets, polls, votes and the voting reward."""

import random
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from config import Database
from db.tournaments import (
    RoundReward, _get_perfect_seeding, advance_winner, check_round_status, claim_round_reward, create_tournament,
    force_close_active_round, get_active_tournament_id, get_bracket_render_data, get_expired_unresolved_matches,
    get_tournament_days, get_tournament_raffle_winner, get_tournament_winner_name, get_unpolled_matches,
    has_polled_matches, process_user_vote, record_vote, remove_user_vote, set_match_poll_data,
    set_tournament_completed
)

NOW = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _databases(databases):
    databases(Database.TOURNAMENTS, Database.MERCH)


def _make(entrant_count=4, name="Bracket", days=2):
    entrants = [f"Song {i}" for i in range(1, entrant_count + 1)]
    return create_tournament(name, "A description", entrants, days)


def _matches(query, tournament_id, round_num=None):
    sql = "SELECT * FROM tournament_matches WHERE tournament_id = ?"
    params = [tournament_id]
    if round_num:
        sql += " AND round_num = ?"
        params.append(round_num)
    return query(Database.TOURNAMENTS, sql + " ORDER BY round_num, match_position", *params)


def _entrant_names(query):
    return {row["entrant_id"]: row["name"] for row in query(Database.TOURNAMENTS, "SELECT * FROM tournament_entrants")}


def _post_polls(query, tournament_id, round_num, end_time=NOW + timedelta(days=2)):
    """Gives every match in the round a poll message (id 1000 + match id) that ends at end_time."""
    for match in _matches(query, tournament_id, round_num):
        set_match_poll_data(match["match_id"], 1000 + match["match_id"], end_time)


def _message_id(query, tournament_id, round_num, position):
    return [m for m in _matches(query, tournament_id, round_num) if m["match_position"] == position][0]["message_id"]


class TestSeeding:
    """The standard bracket order keeps the top seeds apart until late."""

    @pytest.mark.parametrize("size, expected", [
        (2, [1, 2]),
        (4, [1, 4, 2, 3]),
        (8, [1, 8, 4, 5, 2, 7, 3, 6]),
    ])
    def test_known_orders(self, size, expected):
        assert _get_perfect_seeding(size) == expected

    @pytest.mark.parametrize("size", [4, 8, 16, 32, 64])
    def test_every_seed_appears_once_and_each_pair_adds_up_to_size_plus_one(self, size):
        order = _get_perfect_seeding(size)

        assert sorted(order) == list(range(1, size + 1))
        for high, low in zip(order[::2], order[1::2]):
            assert high + low == size + 1

    @pytest.mark.parametrize("size", [4, 8, 16, 32])
    def test_the_top_two_seeds_are_in_opposite_halves(self, size):
        order = _get_perfect_seeding(size)

        assert order.index(1) < size // 2 <= order.index(2)


class TestCreateTournament:
    """create_tournament builds the tournament, entrants and the linked match tree together."""

    def test_returns_a_short_id_and_stores_the_details(self, query):
        tournament_id = _make(name="Best Ballad", days=3)

        assert len(tournament_id) == 8
        row = query(Database.TOURNAMENTS, "SELECT * FROM tournaments")[0]
        assert (row["tournament_id"], row["name"], row["description"], row["days_per_round"], row["status"]) == \
            (tournament_id, "Best Ballad", "A description", 3, "active")

    def test_each_tournament_gets_its_own_id(self):
        assert _make() != _make()

    def test_entrants_are_seeded_in_the_order_given_and_trimmed(self, query):
        create_tournament("T", "d", ["  First ", "Second", "Third", "Fourth"], 2)

        rows = query(Database.TOURNAMENTS, "SELECT name, seed FROM tournament_entrants ORDER BY seed")
        assert [(r["name"], r["seed"]) for r in rows] == [("First", 1), ("Second", 2), ("Third", 3), ("Fourth", 4)]

    @pytest.mark.parametrize("size, matches_per_round", [(2, [1]), (4, [2, 1]), (8, [4, 2, 1]), (16, [8, 4, 2, 1])])
    def test_the_match_tree_has_the_right_shape(self, query, size, matches_per_round):
        tournament_id = _make(size)

        for round_num, expected in enumerate(matches_per_round, start=1):
            assert len(_matches(query, tournament_id, round_num)) == expected

    def test_round_one_pairs_follow_the_seeding(self, query):
        tournament_id = _make(8)
        names = _entrant_names(query)

        pairs = [(names[m["entrant_a_id"]], names[m["entrant_b_id"]]) for m in _matches(query, tournament_id, 1)]

        assert pairs == [("Song 1", "Song 8"), ("Song 4", "Song 5"), ("Song 2", "Song 7"), ("Song 3", "Song 6")]

    def test_later_rounds_start_empty(self, query):
        tournament_id = _make(8)

        for match in _matches(query, tournament_id, 2) + _matches(query, tournament_id, 3):
            assert match["entrant_a_id"] is None and match["entrant_b_id"] is None

    def test_each_match_points_at_the_match_its_winner_plays_next(self, query):
        tournament_id = _make(8)
        by_position = {(m["round_num"], m["match_position"]): m for m in _matches(query, tournament_id)}

        assert by_position[(1, 1)]["next_match_id"] == by_position[(2, 1)]["match_id"]
        assert by_position[(1, 2)]["next_match_id"] == by_position[(2, 1)]["match_id"]
        assert by_position[(1, 3)]["next_match_id"] == by_position[(2, 2)]["match_id"]
        assert by_position[(1, 4)]["next_match_id"] == by_position[(2, 2)]["match_id"]
        assert by_position[(2, 1)]["next_match_id"] == by_position[(3, 1)]["match_id"]
        assert by_position[(3, 1)]["next_match_id"] is None

    def test_a_failure_part_way_creates_nothing(self, query):
        with pytest.raises(AttributeError):
            create_tournament("T", "d", ["a", None, "c", "d"], 2)   # None can't be trimmed

        assert query(Database.TOURNAMENTS, "SELECT * FROM tournaments") == []
        assert query(Database.TOURNAMENTS, "SELECT * FROM tournament_entrants") == []


class TestBracketRenderData:
    """get_bracket_render_data feeds the picture of the bracket."""

    def test_unknown_tournament_is_none(self):
        assert get_bracket_render_data("nope") is None

    def test_a_tournament_with_no_matches_has_nothing_to_draw(self, execute):
        execute(Database.TOURNAMENTS, "INSERT INTO tournaments (tournament_id, name) VALUES ('empty', 'Empty')")

        assert get_bracket_render_data("empty") is None

    def test_a_fresh_four_entrant_bracket(self):
        context = get_bracket_render_data(_make(4, name="Best Ballad"))

        assert context["tournament_title"] == "Best Ballad"
        assert context["total_rounds"] == 2
        assert context["left_rounds"] == [[{"a_seed": 1, "a_name": "Song 1", "b_seed": 4, "b_name": "Song 4"}]]
        assert context["right_rounds"] == [[{"a_seed": 2, "a_name": "Song 2", "b_seed": 3, "b_name": "Song 3"}]]
        assert context["finals"] == {"a_seed": "", "a_name": "", "b_seed": "", "b_name": ""}
        assert context["winner"] == "WINNER"

    def test_half_of_each_round_is_on_each_side(self):
        context = get_bracket_render_data(_make(16))

        assert context["total_rounds"] == 4
        assert [len(r) for r in context["left_rounds"]] == [4, 2, 1]
        assert [len(r) for r in context["right_rounds"]] == [4, 2, 1]

    def test_advancing_a_winner_fills_the_next_round_slot(self, query):
        tournament_id = _make(4)
        first = _matches(query, tournament_id, 1)[0]
        winner = first["entrant_a_id"]
        advance_winner(first["match_id"], tournament_id, 1, 1, winner)

        context = get_bracket_render_data(tournament_id)

        assert context["finals"]["a_name"] == "Song 1"
        assert context["finals"]["b_name"] == ""

    def test_the_winner_is_named_once_the_final_is_decided(self, query):
        tournament_id = _make(2)
        [final] = _matches(query, tournament_id, 1)
        advance_winner(final["match_id"], tournament_id, 1, 1, final["entrant_b_id"])

        assert get_bracket_render_data(tournament_id)["winner"] == "Song 2"


class TestPolls:
    """Matches wait for a poll to be posted, then for it to end."""

    def test_round_one_matches_are_waiting_for_polls(self, query):
        tournament_id = _make(4)

        matches = get_unpolled_matches(tournament_id, 1)

        assert [(m["a_name"], m["b_name"]) for m in matches] == [("Song 1", "Song 4"), ("Song 2", "Song 3")]
        assert query(Database.TOURNAMENTS, "SELECT COUNT(*) AS n FROM tournament_matches")[0]["n"] == 3

    def test_later_rounds_wait_until_both_entrants_are_known(self):
        assert get_unpolled_matches(_make(4), 2) == []

    def test_a_match_with_a_poll_is_no_longer_unpolled(self, query):
        tournament_id = _make(4)
        first = _matches(query, tournament_id, 1)[0]

        set_match_poll_data(first["match_id"], 555, NOW + timedelta(days=2))

        assert [m["match_id"] for m in get_unpolled_matches(tournament_id, 1)] != [first["match_id"]]
        assert len(get_unpolled_matches(tournament_id, 1)) == 1

    def test_poll_data_is_stored_with_the_end_time(self, query):
        tournament_id = _make(4)
        first = _matches(query, tournament_id, 1)[0]

        set_match_poll_data(first["match_id"], 555, NOW)

        row = _matches(query, tournament_id, 1)[0]
        assert (row["message_id"], row["end_timestamp"]) == (555, NOW.isoformat())

    def test_has_polled_matches(self, query):
        tournament_id = _make(4)
        assert has_polled_matches(tournament_id, 1) is False

        set_match_poll_data(_matches(query, tournament_id, 1)[0]["match_id"], 555, NOW)

        assert has_polled_matches(tournament_id, 1) is True
        assert has_polled_matches(tournament_id, 2) is False

    def test_polls_that_have_ended_are_returned_until_resolved(self, query, frozen_time):
        tournament_id = _make(4)
        _post_polls(query, tournament_id, 1, end_time=NOW)

        frozen_time("2026-03-17 11:59:59")
        assert get_expired_unresolved_matches() == []

        frozen_time("2026-03-17 12:00:01")
        expired = get_expired_unresolved_matches()
        assert len(expired) == 2
        assert {"match_id", "tournament_id", "round_num", "match_position", "message_id", "entrant_a_id",
                "entrant_b_id", "entrant_a_seed", "entrant_b_seed"} <= set(expired[0])

    def test_a_resolved_match_is_not_returned(self, query, frozen_time):
        tournament_id = _make(4)
        _post_polls(query, tournament_id, 1, end_time=NOW)
        first = _matches(query, tournament_id, 1)[0]
        advance_winner(first["match_id"], tournament_id, 1, 1, first["entrant_a_id"])
        frozen_time("2026-03-17 13:00:00")

        assert [m["match_id"] for m in get_expired_unresolved_matches()] != [first["match_id"]]
        assert len(get_expired_unresolved_matches()) == 1

    def test_matches_without_a_poll_are_never_expired(self, frozen_time):
        _make(4)
        frozen_time("2030-01-01 00:00:00")

        assert get_expired_unresolved_matches() == []

    def test_force_closing_ends_only_live_unresolved_polls(self, query, frozen_time):
        tournament_id = _make(4)
        _post_polls(query, tournament_id, 1, end_time=NOW + timedelta(days=5))
        first = _matches(query, tournament_id, 1)[0]
        advance_winner(first["match_id"], tournament_id, 1, 1, first["entrant_a_id"])
        frozen_time("2026-03-17 12:00:00")

        assert force_close_active_round(tournament_id) == 1

        # the resolved match keeps its original end time; the live one is now due
        assert [m["match_position"] for m in get_expired_unresolved_matches()] == [2]

    def test_force_closing_with_no_live_polls_changes_nothing(self):
        assert force_close_active_round(_make(4)) == 0


class TestAdvanceAndStatus:
    """advance_winner moves entrants up the tree; check_round_status says where the tournament is."""

    def test_the_winner_of_an_odd_position_becomes_entrant_a_and_even_becomes_b(self, query):
        tournament_id = _make(4)
        first, second = _matches(query, tournament_id, 1)

        advance_winner(first["match_id"], tournament_id, 1, 1, first["entrant_b_id"])
        advance_winner(second["match_id"], tournament_id, 1, 2, second["entrant_a_id"])

        [final] = _matches(query, tournament_id, 2)
        assert final["entrant_a_id"] == first["entrant_b_id"]
        assert final["entrant_b_id"] == second["entrant_a_id"]
        assert _matches(query, tournament_id, 1)[0]["winner_id"] == first["entrant_b_id"]

    def test_status_of_an_unknown_tournament(self):
        assert check_round_status("nope") == {
            "tournament_name": "Unknown", "current_round": 0, "is_finished": False, "is_tournament_over": False}

    def test_a_new_tournament_is_in_round_one(self):
        assert check_round_status(_make(4, name="Ballads")) == {
            "tournament_name": "Ballads", "current_round": 1, "is_finished": False, "is_tournament_over": False}

    def test_a_round_is_unfinished_until_every_match_has_a_winner(self, query):
        tournament_id = _make(4)
        first = _matches(query, tournament_id, 1)[0]
        advance_winner(first["match_id"], tournament_id, 1, 1, first["entrant_a_id"])

        assert check_round_status(tournament_id)["current_round"] == 1

    def test_the_status_moves_to_the_next_round_when_one_finishes(self, query):
        tournament_id = _make(4)
        for position, match in enumerate(_matches(query, tournament_id, 1), start=1):
            advance_winner(match["match_id"], tournament_id, 1, position, match["entrant_a_id"])

        status = check_round_status(tournament_id)

        assert (status["current_round"], status["is_finished"], status["is_tournament_over"]) == (2, False, False)

    def test_the_tournament_is_over_when_the_final_has_a_winner(self, query):
        tournament_id = _make(2, name="Two")
        [final] = _matches(query, tournament_id, 1)
        advance_winner(final["match_id"], tournament_id, 1, 1, final["entrant_a_id"])

        assert check_round_status(tournament_id) == {
            "tournament_name": "Two", "current_round": 1, "is_finished": True, "is_tournament_over": True}

    def test_days_per_round_and_its_default(self):
        assert get_tournament_days(_make(4, days=5)) == 5
        assert get_tournament_days("nope") == 1

    def test_the_winners_name_and_its_fallback(self, query):
        tournament_id = _make(2)
        assert get_tournament_winner_name(tournament_id) == "Unknown Artist"

        [final] = _matches(query, tournament_id, 1)
        advance_winner(final["match_id"], tournament_id, 1, 1, final["entrant_b_id"])

        assert get_tournament_winner_name(tournament_id) == "Song 2"


class TestTournamentStatus:
    """The background task follows the most recent active tournament."""

    def test_no_tournaments(self):
        assert get_active_tournament_id() is None

    def test_the_most_recently_created_active_one_is_returned(self, execute):
        older, newer = _make(), _make()
        execute(Database.TOURNAMENTS, "UPDATE tournaments SET created_at = '2026-01-01 00:00:00' "
                                      "WHERE tournament_id = ?", older)
        execute(Database.TOURNAMENTS, "UPDATE tournaments SET created_at = '2026-02-01 00:00:00' "
                                      "WHERE tournament_id = ?", newer)

        assert get_active_tournament_id() == newer

    def test_completing_it_hands_over_to_the_previous_one(self, execute):
        older, newer = _make(), _make()
        execute(Database.TOURNAMENTS, "UPDATE tournaments SET created_at = '2026-01-01 00:00:00' "
                                      "WHERE tournament_id = ?", older)
        execute(Database.TOURNAMENTS, "UPDATE tournaments SET created_at = '2026-02-01 00:00:00' "
                                      "WHERE tournament_id = ?", newer)

        assert set_tournament_completed(newer) is True

        assert get_active_tournament_id() == older

    def test_completing_an_unknown_tournament_is_false(self):
        assert set_tournament_completed("nope") is False


class TestVotes:
    """Votes are recorded by poll message and answer (1 = first entrant, 2 = second)."""

    @pytest.fixture
    def polled(self, query):
        tournament_id = _make(4)
        _post_polls(query, tournament_id, 1)
        return tournament_id

    def test_a_vote_for_an_unknown_poll_is_ignored(self, query):
        assert record_vote(999999, 1, 1) is None
        assert query(Database.TOURNAMENTS, "SELECT * FROM tournament_votes") == []

    def test_answer_one_votes_for_the_first_entrant_and_two_for_the_second(self, polled, query):
        first_poll = _message_id(query, polled, 1, 1)
        match = _matches(query, polled, 1)[0]

        assert record_vote(first_poll, 10, 1) == (polled, 1)
        record_vote(first_poll, 11, 2)

        rows = query(Database.TOURNAMENTS, "SELECT * FROM tournament_votes")
        votes = {r["user_id"]: r["choice_entrant_id"] for r in rows}
        assert votes == {10: match["entrant_a_id"], 11: match["entrant_b_id"]}

    def test_changing_a_vote_replaces_it(self, polled, query):
        first_poll = _message_id(query, polled, 1, 1)
        match = _matches(query, polled, 1)[0]
        record_vote(first_poll, 10, 1)

        record_vote(first_poll, 10, 2)

        rows = query(Database.TOURNAMENTS, "SELECT * FROM tournament_votes")
        assert [r["choice_entrant_id"] for r in rows] == [match["entrant_b_id"]]

    def test_removing_a_vote(self, polled, query):
        first_poll = _message_id(query, polled, 1, 1)
        record_vote(first_poll, 10, 1)

        assert remove_user_vote(first_poll, 10, 1) is True

        assert query(Database.TOURNAMENTS, "SELECT * FROM tournament_votes") == []

    def test_removing_the_old_choice_does_not_delete_a_vote_that_has_since_changed(self, polled, query):
        # Changing a vote in Discord removes the old answer and adds the new one, in either order
        first_poll = _message_id(query, polled, 1, 1)
        match = _matches(query, polled, 1)[0]
        record_vote(first_poll, 10, 2)

        assert remove_user_vote(first_poll, 10, 1) is False

        rows = query(Database.TOURNAMENTS, "SELECT * FROM tournament_votes")
        assert [r["choice_entrant_id"] for r in rows] == [match["entrant_b_id"]]

    def test_removing_a_vote_that_was_never_cast_is_false(self, polled, query):
        assert remove_user_vote(_message_id(query, polled, 1, 1), 10, 1) is False

    def test_removing_from_an_unknown_poll_is_false(self):
        assert remove_user_vote(999999, 10, 1) is False


class TestRoundReward:
    """Voting in every matchup of a round earns one heart, once."""

    @pytest.fixture
    def polled(self, query):
        tournament_id = _make(4, name="Ballads")
        _post_polls(query, tournament_id, 1)
        return tournament_id

    def _vote_in_all(self, query, tournament_id, user_id):
        rewards = [process_user_vote(m["message_id"], user_id, 1) for m in _matches(query, tournament_id, 1)]
        return rewards

    def test_no_reward_until_every_matchup_has_a_vote(self, polled, query):
        first_poll = _message_id(query, polled, 1, 1)

        assert process_user_vote(first_poll, 10, 1) is None

        assert query(Database.MERCH, "SELECT * FROM users") == []

    def test_the_vote_that_completes_the_round_pays_one_heart(self, polled, query):
        rewards = self._vote_in_all(query, polled, 10)

        assert rewards == [None, RoundReward(polled, "Ballads", 1)]
        assert query(Database.MERCH, "SELECT balance FROM users WHERE user_id = 10")[0]["balance"] == 1
        tx = query(Database.MERCH, "SELECT * FROM transactions")[0]
        assert (tx["receiver_id"], tx["amount"]) == (10, 1)
        assert tx["reason"] == "Voted in every matchup for round 1 of **Ballads**"

    def test_it_is_only_paid_once_however_many_times_they_vote_again(self, polled, query):
        self._vote_in_all(query, polled, 10)

        again = self._vote_in_all(query, polled, 10)
        changed = process_user_vote(_message_id(query, polled, 1, 1), 10, 2)

        assert again == [None, None] and changed is None
        assert query(Database.MERCH, "SELECT balance FROM users WHERE user_id = 10")[0]["balance"] == 1
        assert len(query(Database.TOURNAMENTS, "SELECT * FROM tournament_rewards_ledger")) == 1

    def test_each_voter_is_paid_separately(self, polled, query):
        self._vote_in_all(query, polled, 10)
        self._vote_in_all(query, polled, 11)

        balances = {r["user_id"]: r["balance"] for r in query(Database.MERCH, "SELECT * FROM users")}
        assert balances == {10: 1, 11: 1}

    def test_a_reward_is_per_round(self, polled, query):
        self._vote_in_all(query, polled, 10)
        for position, match in enumerate(_matches(query, polled, 1), start=1):
            advance_winner(match["match_id"], polled, 1, position, match["entrant_a_id"])
        _post_polls(query, polled, 2)

        [final] = _matches(query, polled, 2)
        reward = process_user_vote(final["message_id"], 10, 1)

        assert reward == RoundReward(polled, "Ballads", 2)
        assert query(Database.MERCH, "SELECT balance FROM users WHERE user_id = 10")[0]["balance"] == 2

    def test_a_vote_on_a_non_tournament_poll_is_ignored(self):
        assert process_user_vote(424242, 10, 1) is None

    def test_if_the_payment_fails_the_user_is_not_marked_as_paid(self, polled, query, execute):
        # Pay attempt fails inside the shared transaction, so the ledger entry must roll back with it
        execute(Database.MERCH, "DROP TABLE transactions")
        first, second = [m["message_id"] for m in _matches(query, polled, 1)]
        process_user_vote(first, 10, 1)

        with pytest.raises(sqlite3.OperationalError):
            process_user_vote(second, 10, 1)

        assert query(Database.TOURNAMENTS, "SELECT * FROM tournament_rewards_ledger") == []
        assert query(Database.MERCH, "SELECT * FROM users") == []

    def test_a_reward_that_failed_is_paid_on_the_next_vote(self, polled, query, execute):
        first, second = [m["message_id"] for m in _matches(query, polled, 1)]
        process_user_vote(first, 10, 1)
        execute(Database.MERCH, "ALTER TABLE transactions RENAME TO transactions_away")
        with pytest.raises(sqlite3.OperationalError):
            process_user_vote(second, 10, 1)
        execute(Database.MERCH, "ALTER TABLE transactions_away RENAME TO transactions")

        assert process_user_vote(second, 10, 1) == RoundReward(polled, "Ballads", 1)

    def test_two_votes_at_once_pay_only_one_heart(self, polled, query):
        first, second = [m["message_id"] for m in _matches(query, polled, 1)]
        record_vote(first, 10, 1)
        record_vote(second, 10, 1)
        gate = threading.Barrier(2)
        results = []

        def claim():
            gate.wait()
            results.append(claim_round_reward(polled, 1, 10))

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len([r for r in results if r]) == 1
        assert query(Database.MERCH, "SELECT balance FROM users WHERE user_id = 10")[0]["balance"] == 1


class TestRaffleWinner:
    """Every vote is a raffle ticket, and the winner is drawn weighted by tickets."""

    @pytest.fixture
    def voted(self, query):
        tournament_id = _make(4)
        _post_polls(query, tournament_id, 1)
        first, second = [m["message_id"] for m in _matches(query, tournament_id, 1)]
        record_vote(first, 10, 1)      # user 10 has two tickets
        record_vote(second, 10, 1)
        record_vote(first, 11, 2)      # user 11 has one
        return tournament_id

    def test_nobody_voted(self):
        assert get_tournament_raffle_winner(_make(4)) is None

    def test_an_unknown_tournament_has_no_winner(self):
        assert get_tournament_raffle_winner("nope") is None

    def test_a_sole_voter_always_wins(self, query):
        tournament_id = _make(4)
        _post_polls(query, tournament_id, 1)
        record_vote(_message_id(query, tournament_id, 1, 1), 10, 1)

        assert get_tournament_raffle_winner(tournament_id) == {"user_id": 10, "tickets": 1, "total_pool": 1}

    def test_the_draw_is_weighted_by_tickets(self, voted, monkeypatch):
        seen = {}

        def fake_choices(population, weights, **_):
            seen.update(zip(population, weights))
            return [population[0]]

        monkeypatch.setattr(random, "choices", fake_choices)

        get_tournament_raffle_winner(voted)

        assert seen == {10: 2, 11: 1}

    def test_the_pool_is_the_total_number_of_votes(self, voted):
        assert get_tournament_raffle_winner(voted)["total_pool"] == 3

    def test_a_chosen_winner_is_described_not_redrawn(self, voted, monkeypatch):
        monkeypatch.setattr(random, "choices", lambda *_, **__: pytest.fail("must not draw again"))

        assert get_tournament_raffle_winner(voted, winner_id=11) == {"user_id": 11, "tickets": 1, "total_pool": 3}

    def test_a_chosen_winner_who_no_longer_has_tickets_has_zero(self, voted):
        assert get_tournament_raffle_winner(voted, winner_id=99)["tickets"] == 0

    def test_the_odds_follow_the_ticket_counts(self, voted):
        random.seed(1234)
        wins = {10: 0, 11: 0}
        for _ in range(600):
            wins[get_tournament_raffle_winner(voted)["user_id"]] += 1

        assert 300 < wins[10] < 480       # expected 400 of 600
