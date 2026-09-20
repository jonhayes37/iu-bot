"""Tests for db/hall_of_fame.py

Every function works on the current awards year (December 1 to November 30).
"""

import sqlite3

import pytest

from config import Database
from db.hall_of_fame import (
    get_all_hof_nominations, get_hof_nomination, get_official_hof_nominees, get_user_hof_vote,
    save_hof_nomination, save_hof_vote, set_hof_final_nominees
)


@pytest.fixture(autouse=True)
def _hall_of_fame_database(databases, frozen_time):
    databases(Database.HALL_OF_FAME)
    frozen_time("2026-10-15 12:00:00")


class TestNominations:
    """One nomination per member per year, which they can change."""

    def test_saving_returns_the_year(self):
        assert save_hof_nomination(1, "jo", "Girls' Generation") == 2026

    def test_a_december_nomination_is_for_next_year(self, frozen_time):
        frozen_time("2026-12-02 12:00:00")

        assert save_hof_nomination(1, "jo", "Girls' Generation") == 2027

    def test_the_saved_nomination_can_be_read_back(self):
        save_hof_nomination(1, "jo", "Girls' Generation")

        assert get_hof_nomination(1) == "Girls' Generation"

    def test_no_nomination_is_none(self):
        assert get_hof_nomination(1) is None

    def test_saving_again_replaces_it(self, query):
        save_hof_nomination(1, "jo", "first")

        save_hof_nomination(1, "jo", "second")

        assert get_hof_nomination(1) == "second"
        assert len(query(Database.HALL_OF_FAME, "SELECT * FROM hall_of_fame_nominations")) == 1

    def test_last_years_nomination_is_not_this_years(self, frozen_time):
        save_hof_nomination(1, "jo", "old")
        frozen_time("2027-03-01 12:00:00")

        assert get_hof_nomination(1) is None

    def test_export_lists_this_years_nominations_only(self, frozen_time):
        save_hof_nomination(1, "old timer", "last year")
        frozen_time("2027-03-01 12:00:00")
        save_hof_nomination(2, "a", "x")
        save_hof_nomination(3, "b", "y")

        rows = get_all_hof_nominations()

        assert sorted((row["username"], row["nomination_text"]) for row in rows) == [("a", "x"), ("b", "y")]


class TestFinalNominees:
    """The vetted list the ballot is built from."""

    def test_none_set_yet(self):
        assert get_official_hof_nominees() == []

    def test_set_returns_the_year_and_the_list_comes_back_sorted(self):
        assert set_hof_final_nominees(["IU", "BTS", "Big Bang"]) == 2026

        assert get_official_hof_nominees() == ["BTS", "Big Bang", "IU"]

    def test_setting_again_replaces_the_list(self):
        set_hof_final_nominees(["IU", "BTS"])

        set_hof_final_nominees(["EXO"])

        assert get_official_hof_nominees() == ["EXO"]

    def test_setting_an_empty_list_clears_it(self):
        set_hof_final_nominees(["IU"])

        set_hof_final_nominees([])

        assert get_official_hof_nominees() == []

    def test_only_the_current_year_is_replaced(self, frozen_time):
        set_hof_final_nominees(["IU"])
        frozen_time("2027-03-01 12:00:00")

        set_hof_final_nominees(["EXO"])
        frozen_time("2026-10-15 12:00:00")

        assert get_official_hof_nominees() == ["IU"]

    def test_the_same_name_twice_is_rejected_and_the_old_list_is_kept(self):
        set_hof_final_nominees(["IU"])

        with pytest.raises(sqlite3.IntegrityError):  # the (year, name) primary key
            set_hof_final_nominees(["EXO", "EXO"])

        assert get_official_hof_nominees() == ["IU"]


class TestVotes:
    """A ranked ballot of three per member per year."""

    def test_no_vote_is_none(self):
        assert get_user_hof_vote(1) is None

    def test_a_saved_vote_comes_back_in_order(self):
        assert save_hof_vote(1, "IU", "BTS", "EXO") == 2026

        assert get_user_hof_vote(1) == {"first_choice": "IU", "second_choice": "BTS", "third_choice": "EXO"}

    def test_voting_again_replaces_the_ballot(self, query):
        save_hof_vote(1, "IU", "BTS", "EXO")

        save_hof_vote(1, "EXO", "IU", "BTS")

        assert get_user_hof_vote(1)["first_choice"] == "EXO"
        assert len(query(Database.HALL_OF_FAME, "SELECT * FROM hall_of_fame_votes")) == 1

    def test_votes_are_per_member(self):
        save_hof_vote(1, "IU", "BTS", "EXO")
        save_hof_vote(2, "BTS", "IU", "EXO")

        assert get_user_hof_vote(2)["first_choice"] == "BTS"

    def test_last_years_ballot_is_not_this_years(self, frozen_time):
        save_hof_vote(1, "IU", "BTS", "EXO")
        frozen_time("2027-03-01 12:00:00")

        assert get_user_hof_vote(1) is None
