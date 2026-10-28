"""Tests for db/hall_of_fame.py

Every function works on the awards year it is given (the year of the hub or command that asked).
"""

import sqlite3

import pytest

from config import Database
from db.hall_of_fame import (
    get_all_hof_nominations, get_hof_nomination, get_official_hof_nominees, get_user_hof_vote,
    save_hof_nomination, save_hof_vote, set_hof_final_nominees
)


@pytest.fixture(autouse=True)
def _hall_of_fame_database(databases):
    databases(Database.HALL_OF_FAME)


class TestNominations:
    """One nomination per member per year, which they can change."""

    def test_the_nomination_is_saved_for_the_year(self, query):
        save_hof_nomination(2026, 1, "jo", "Girls' Generation")

        [row] = query(Database.HALL_OF_FAME, "SELECT * FROM hall_of_fame_nominations")
        assert (row["award_year"], row["user_id"], row["username"]) == (2026, 1, "jo")

    def test_the_saved_nomination_can_be_read_back(self):
        save_hof_nomination(2026, 1, "jo", "Girls' Generation")

        assert get_hof_nomination(2026, 1) == "Girls' Generation"

    def test_no_nomination_is_none(self):
        assert get_hof_nomination(2026, 1) is None

    def test_saving_again_replaces_it(self, query):
        save_hof_nomination(2026, 1, "jo", "first")

        save_hof_nomination(2026, 1, "jo", "second")

        assert get_hof_nomination(2026, 1) == "second"
        assert len(query(Database.HALL_OF_FAME, "SELECT * FROM hall_of_fame_nominations")) == 1

    def test_another_years_nomination_is_not_this_years(self):
        save_hof_nomination(2025, 1, "jo", "old")

        assert get_hof_nomination(2026, 1) is None

    def test_export_lists_the_years_nominations_only(self):
        save_hof_nomination(2025, 1, "old timer", "last year")
        save_hof_nomination(2026, 2, "a", "x")
        save_hof_nomination(2026, 3, "b", "y")

        rows = get_all_hof_nominations(2026)

        assert sorted((row["username"], row["nomination_text"]) for row in rows) == [("a", "x"), ("b", "y")]


class TestFinalNominees:
    """The vetted list the ballot is built from."""

    def test_none_set_yet(self):
        assert get_official_hof_nominees(2026) == []

    def test_the_list_comes_back_sorted(self):
        set_hof_final_nominees(2026, ["IU", "BTS", "Big Bang"])

        assert get_official_hof_nominees(2026) == ["BTS", "Big Bang", "IU"]

    def test_setting_again_replaces_the_list(self):
        set_hof_final_nominees(2026, ["IU", "BTS"])

        set_hof_final_nominees(2026, ["EXO"])

        assert get_official_hof_nominees(2026) == ["EXO"]

    def test_setting_an_empty_list_clears_it(self):
        set_hof_final_nominees(2026, ["IU"])

        set_hof_final_nominees(2026, [])

        assert get_official_hof_nominees(2026) == []

    def test_only_the_given_year_is_replaced(self):
        set_hof_final_nominees(2026, ["IU"])

        set_hof_final_nominees(2027, ["EXO"])

        assert get_official_hof_nominees(2026) == ["IU"]

    def test_the_same_name_twice_is_rejected_and_the_old_list_is_kept(self):
        set_hof_final_nominees(2026, ["IU"])

        with pytest.raises(sqlite3.IntegrityError):  # the (year, name) primary key
            set_hof_final_nominees(2026, ["EXO", "EXO"])

        assert get_official_hof_nominees(2026) == ["IU"]


class TestVotes:
    """A ranked ballot of three per member per year."""

    def test_no_vote_is_none(self):
        assert get_user_hof_vote(2026, 1) is None

    def test_a_saved_vote_comes_back_in_order(self):
        save_hof_vote(2026, 1, "IU", "BTS", "EXO")

        assert get_user_hof_vote(2026, 1) == {"first_choice": "IU", "second_choice": "BTS", "third_choice": "EXO"}

    def test_voting_again_replaces_the_ballot(self, query):
        save_hof_vote(2026, 1, "IU", "BTS", "EXO")

        save_hof_vote(2026, 1, "EXO", "IU", "BTS")

        assert get_user_hof_vote(2026, 1)["first_choice"] == "EXO"
        assert len(query(Database.HALL_OF_FAME, "SELECT * FROM hall_of_fame_votes")) == 1

    def test_votes_are_per_member(self):
        save_hof_vote(2026, 1, "IU", "BTS", "EXO")
        save_hof_vote(2026, 2, "BTS", "IU", "EXO")

        assert get_user_hof_vote(2026, 2)["first_choice"] == "BTS"

    def test_another_years_ballot_is_not_this_years(self):
        save_hof_vote(2025, 1, "IU", "BTS", "EXO")

        assert get_user_hof_vote(2026, 1) is None
