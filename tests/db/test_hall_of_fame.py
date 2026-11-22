"""Tests for db/hall_of_fame.py

Every function works on the awards year it is given (the year of the hub or command that asked).
"""

import sqlite3
from typing import Callable, NamedTuple

import pytest

from config import Database
from db.hall_of_fame import (
    Inductee, add_hall_of_famer, add_lifetime_achiever, find_hall_of_famer, find_lifetime_achiever,
    get_all_hof_nominations, get_hall_of_famers, get_hof_ballots, get_hof_nomination, get_lifetime_achievers,
    get_official_hof_nominees, get_user_hof_vote, save_hof_nomination, save_hof_vote, set_hof_final_nominees
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


class TestBallots:
    """get_hof_ballots reads back every ballot for counting."""

    def test_no_votes(self):
        assert get_hof_ballots(2026) == []

    def test_every_ballot_for_the_year_in_choice_order(self):
        save_hof_vote(2026, 1, "IU", "BTS", "EXO")
        save_hof_vote(2026, 2, "BTS", "IU", "EXO")
        save_hof_vote(2025, 3, "Old", "Older", "Oldest")

        assert sorted(get_hof_ballots(2026)) == [("BTS", "IU", "EXO"), ("IU", "BTS", "EXO")]


class InducteeList(NamedTuple):
    """The functions for one of the two lists, which keep the same record."""
    add: Callable[[str, int], bool]
    find: Callable[[str], Inductee | None]
    get_all: Callable[[], list[Inductee]]
    table: str


INDUCTEE_LISTS = [
    pytest.param(InducteeList(add_hall_of_famer, find_hall_of_famer, get_hall_of_famers, "hall_of_famers"),
                 id="hall of fame"),
    pytest.param(InducteeList(add_lifetime_achiever, find_lifetime_achiever, get_lifetime_achievers,
                              "lifetime_achievers"), id="lifetime achievement"),
]


@pytest.mark.usefixtures("no_inductees")
@pytest.mark.parametrize("inductees", INDUCTEE_LISTS)
class TestInductees:
    """Who has been inducted, and when. Each name is in a list once."""

    def test_with_nobody_inducted_the_list_is_empty(self, inductees):
        assert inductees.get_all() == []
        assert inductees.find("IU") is None

    def test_adding_stores_the_name_and_year(self, inductees, query):
        assert inductees.add("IU", 2026) is True

        rows = query(Database.HALL_OF_FAME, f"SELECT * FROM {inductees.table}")
        assert [tuple(row) for row in rows] == [("IU", 2026)]

    def test_a_name_already_in_is_not_added_again_whatever_its_capitals(self, inductees):
        inductees.add("Girls' Generation", 2024)

        assert inductees.add("girls' GENERATION", 2026) is False

        assert inductees.get_all() == [Inductee("Girls' Generation", 2024)]
        assert inductees.find("GIRLS' GENERATION") == Inductee("Girls' Generation", 2024)

    def test_everyone_is_listed_oldest_first_then_by_name(self, inductees):
        for name, year in [("BTS", 2025), ("iu", 2024), ("EXO", 2024), ("2NE1", 2025)]:
            inductees.add(name, year)

        assert inductees.get_all() == [Inductee("EXO", 2024), Inductee("iu", 2024), Inductee("2NE1", 2025),
                                       Inductee("BTS", 2025)]


@pytest.mark.usefixtures("no_inductees")
def test_the_two_lists_are_separate():
    add_hall_of_famer("IU", 2024)

    assert add_lifetime_achiever("IU", 2026) is True
    assert get_hall_of_famers() == [Inductee("IU", 2024)]
    assert get_lifetime_achievers() == [Inductee("IU", 2026)]


class TestSeededInductees:
    """The schema seeds everyone inducted before the commands existed."""

    def test_three_hall_of_famers_a_year_from_2020_to_2025(self):
        hall_of_famers = get_hall_of_famers()

        assert len(hall_of_famers) == 18
        assert {year: sum(1 for i in hall_of_famers if i.year_inducted == year) for year in range(2020, 2026)} == \
            dict.fromkeys(range(2020, 2026), 3)
        assert hall_of_famers[:3] == [Inductee("Boa", 2020), Inductee("BTS", 2020), Inductee("Girls' Generation", 2020)]
        assert find_hall_of_famer("Kenzie") == Inductee("Kenzie", 2025)

    def test_one_lifetime_achiever_a_year_from_2020_to_2025(self):
        assert get_lifetime_achievers() == [
            Inductee("IU", 2020), Inductee("Psy", 2021), Inductee("JYP", 2022), Inductee("Min Hee Jin", 2023),
            Inductee("Shinsadong Tiger", 2024), Inductee("Teddy", 2025)]

    def test_restarting_doesnt_seed_them_twice_or_undo_later_inductions(self, databases):
        add_hall_of_famer("Mamamoo", 2026)

        databases(Database.HALL_OF_FAME)  # initializes the same database again, as a restart does

        assert len(get_hall_of_famers()) == 19
        assert len(get_lifetime_achievers()) == 6
