"""Tests for db/hmas.py: the HallyU Music Awards.

Every function about one year's awards works on the awards year it is given.
"""

import sqlite3

import pytest

from config import Database
from db.initialize import initialize_databases
from db.hmas import (
    MAX_CATEGORIES_PER_FAMILY, AddCategoryResult, RemoveCategoryResult,
    add_category, get_active_hma_categories, get_all_category_suggestions,
    get_current_categories_by_family, get_hma_ballots, get_hma_final_nominees,
    get_user_category_suggestion, get_user_hma_votes, get_user_nominations, get_yearly_export_data, remove_category,
    replace_user_nominations, save_category_suggestion, save_hma_vote, set_final_nominees
)


@pytest.fixture(autouse=True)
def _hmas_database(databases):
    databases(Database.HMAS)


def _family(display_name):
    """A family's active categories as (category_id, name), sorted by name."""
    return [(c["category_id"], c["name"]) for c in get_active_hma_categories() if c["family"] == display_name]


def _nominate(year, user_id, category_ids, text):
    replace_user_nominations(year, user_id, {category_id: [text] for category_id in category_ids})


class TestSeedData:
    """The three award families and their categories come with the schema."""

    def test_the_families_exist(self, query):
        families = {row["family_id"] for row in query(Database.HMAS, "SELECT family_id FROM hma_families")}

        assert families == {"daesang", "bonsang", "fun"}

    def test_the_daesangs_are_the_four_big_awards(self):
        names = [name for _, name in _family("Daesang")]

        assert names == ["Album of the Year", "Artist of the Year", "Music Video of the Year", "Song of the Year"]

    def test_every_category_belongs_to_a_family(self, query):
        orphans = query(Database.HMAS, "SELECT * FROM hma_categories WHERE family_id NOT IN "
                                       "(SELECT family_id FROM hma_families)")

        assert orphans == []

    def test_starting_up_again_does_not_duplicate_the_seed_data(self, query):
        before = len(query(Database.HMAS, "SELECT * FROM hma_categories"))

        initialize_databases()

        assert len(query(Database.HMAS, "SELECT * FROM hma_categories")) == before

    def test_no_family_has_more_categories_than_the_most_allowed(self):
        for family in ("Daesang", "Bonsang", "Fun"):
            assert 0 < len(_family(family)) <= MAX_CATEGORIES_PER_FAMILY


class TestUserNominations:
    """A member's nominations: any number per category, replaced a category at a time."""

    def test_none_yet(self):
        assert not get_user_nominations(2026, 1)

    def test_saved_nominations_come_back_by_category_in_order(self, query):
        replace_user_nominations(2026, 1, {"soty": ["IVE - HEYA", "aespa - Supernova"], "aoty": ["IU - The Winning"]})

        assert get_user_nominations(2026, 1) == {"soty": ["IVE - HEYA", "aespa - Supernova"],
                                                 "aoty": ["IU - The Winning"]}
        assert {row["award_year"] for row in query(Database.HMAS, "SELECT award_year FROM hma_nominations")} == {2026}

    def test_saving_a_category_again_replaces_only_that_category(self):
        replace_user_nominations(2026, 1, {"soty": ["A", "B"], "aoty": ["C"]})

        replace_user_nominations(2026, 1, {"soty": ["D"]})

        assert get_user_nominations(2026, 1) == {"soty": ["D"], "aoty": ["C"]}

    def test_an_empty_list_clears_the_category(self):
        replace_user_nominations(2026, 1, {"soty": ["A"], "aoty": ["C"]})

        replace_user_nominations(2026, 1, {"soty": []})

        assert get_user_nominations(2026, 1) == {"aoty": ["C"]}

    def test_members_and_years_are_kept_apart(self):
        replace_user_nominations(2026, 1, {"soty": ["mine"]})
        replace_user_nominations(2026, 2, {"soty": ["theirs"]})
        replace_user_nominations(2025, 1, {"soty": ["last year"]})

        replace_user_nominations(2026, 1, {"soty": ["changed"]})

        assert get_user_nominations(2026, 2) == {"soty": ["theirs"]}
        assert get_user_nominations(2025, 1) == {"soty": ["last year"]}

    def test_an_unknown_category_saves_nothing_at_all(self, query):
        with pytest.raises(sqlite3.IntegrityError):
            replace_user_nominations(2026, 1, {"soty": ["IVE - HEYA"], "not_a_category": ["x"]})

        assert query(Database.HMAS, "SELECT * FROM hma_nominations") == []


class TestYearlyExport:
    """get_yearly_export_data groups nominations by family then category."""

    def test_nothing_nominated(self):
        assert not get_yearly_export_data(2026)

    def test_groups_by_family_and_category_with_who_nominated(self):
        _nominate(2026, 1, ["soty", "best_gg"], "IVE - HEYA")
        _nominate(2026, 2, ["soty"], "aespa - Supernova")

        data = get_yearly_export_data(2026)

        assert data["Daesang"]["Song of the Year"] == [(1, "IVE - HEYA"), (2, "aespa - Supernova")]
        assert data["Bonsang"]["Best Girl Group"] == [(1, "IVE - HEYA")]

    def test_only_the_requested_year_is_returned(self):
        _nominate(2026, 1, ["soty"], "this year")
        _nominate(2027, 2, ["soty"], "next year")

        assert get_yearly_export_data(2026)["Daesang"]["Song of the Year"] == [(1, "this year")]
        assert get_yearly_export_data(2027)["Daesang"]["Song of the Year"] == [(2, "next year")]

    def test_a_year_with_nothing_is_empty(self):
        _nominate(2026, 1, ["soty"], "x")

        assert not get_yearly_export_data(2020)


class TestFinalNominees:
    """The vetted list for a category."""

    def test_none_yet(self):
        assert get_hma_final_nominees(2026, "soty") == []

    def test_set_says_it_worked_and_they_come_back_sorted(self):
        assert set_final_nominees(2026, "soty", ["IVE - HEYA", "aespa - Supernova", "BTS - Dynamite"]) is True

        assert get_hma_final_nominees(2026, "soty") == ["BTS - Dynamite", "IVE - HEYA", "aespa - Supernova"]

    def test_setting_again_replaces_the_list(self):
        set_final_nominees(2026, "soty", ["A", "B"])

        set_final_nominees(2026, "soty", ["C"])

        assert get_hma_final_nominees(2026, "soty") == ["C"]

    def test_categories_are_independent(self):
        set_final_nominees(2026, "soty", ["A"])
        set_final_nominees(2026, "aoty", ["B"])

        assert get_hma_final_nominees(2026, "soty") == ["A"]
        assert get_hma_final_nominees(2026, "aoty") == ["B"]

    def test_only_the_given_year_is_replaced(self):
        set_final_nominees(2026, "soty", ["this year"])

        set_final_nominees(2027, "soty", ["next year"])

        assert get_hma_final_nominees(2026, "soty") == ["this year"]

    def test_an_unknown_category_returns_false_and_changes_nothing(self, query):
        assert set_final_nominees(2026, "not_a_category", ["A"]) is False

        assert query(Database.HMAS, "SELECT * FROM hma_final_nominees") == []

    def test_an_unknown_category_does_not_wipe_anything_else(self):
        set_final_nominees(2026, "soty", ["A"])

        set_final_nominees(2026, "not_a_category", ["B"])

        assert get_hma_final_nominees(2026, "soty") == ["A"]

    def test_an_empty_list_clears_the_category(self):
        set_final_nominees(2026, "soty", ["A"])

        set_final_nominees(2026, "soty", [])

        assert get_hma_final_nominees(2026, "soty") == []


class TestVotes:
    """A ranked ballot of three per member per category."""

    def test_no_votes_yet(self):
        assert get_user_hma_votes(2026, 1) == {}

    def test_votes_are_keyed_by_category(self):
        save_hma_vote(2026, 1, "soty", "A", "B", "C")
        save_hma_vote(2026, 1, "aoty", "D", "E", "F")

        votes = get_user_hma_votes(2026, 1)

        assert set(votes) == {"soty", "aoty"}
        assert votes["soty"] == {"category_id": "soty", "first_choice": "A", "second_choice": "B", "third_choice": "C"}

    def test_voting_again_in_a_category_replaces_the_ballot(self, query):
        save_hma_vote(2026, 1, "soty", "A", "B", "C")

        save_hma_vote(2026, 1, "soty", "C", "B", "A")

        assert get_user_hma_votes(2026, 1)["soty"]["first_choice"] == "C"
        assert len(query(Database.HMAS, "SELECT * FROM hma_votes")) == 1

    def test_votes_are_per_member(self):
        save_hma_vote(2026, 1, "soty", "A", "B", "C")

        assert get_user_hma_votes(2026, 2) == {}

    def test_another_years_votes_are_not_this_years(self):
        save_hma_vote(2025, 1, "soty", "A", "B", "C")

        assert get_user_hma_votes(2026, 1) == {}


class TestCategorySuggestions:
    """Members suggest categories to add or drop."""

    def test_none_yet(self):
        assert get_user_category_suggestion(2026, 1) is None
        assert get_all_category_suggestions(2026) == []

    def test_a_suggestion_is_saved_for_the_year_and_can_be_read_back(self, query):
        save_category_suggestion(2026, 1, "jo", "Best Fancam", "Best Band")

        assert query(Database.HMAS, "SELECT award_year FROM hma_category_suggestions")[0]["award_year"] == 2026
        assert get_user_category_suggestion(2026, 1) == {
            "new_categories": "Best Fancam", "dropped_categories": "Best Band"}

    def test_suggesting_again_replaces_the_earlier_one(self):
        save_category_suggestion(2026, 1, "jo", "first", "")

        save_category_suggestion(2026, 1, "jo", "second", "")

        assert get_user_category_suggestion(2026, 1)["new_categories"] == "second"
        assert len(get_all_category_suggestions(2026)) == 1

    def test_another_years_suggestion_is_not_this_years(self):
        save_category_suggestion(2025, 1, "jo", "x", "y")

        assert get_user_category_suggestion(2026, 1) is None

    def test_export_lists_the_years_suggestions(self):
        save_category_suggestion(2025, 1, "old", "x", "y")
        save_category_suggestion(2026, 2, "a", "x", "y")
        save_category_suggestion(2026, 3, "b", "x", "y")

        assert sorted(row["username"] for row in get_all_category_suggestions(2026)) == ["a", "b"]

    def test_either_field_can_be_empty(self):
        save_category_suggestion(2026, 1, "jo", None, None)

        assert get_user_category_suggestion(2026, 1) == {"new_categories": None, "dropped_categories": None}


class TestCategoryLists:
    """The lists of categories shown to admins, on the ballot and in the suggestions post."""

    def test_active_categories_come_daesangs_first_then_by_name(self):
        categories = get_active_hma_categories()

        families = [c["family"] for c in categories]
        assert families == sorted(families, key=["Daesang", "Bonsang", "Fun"].index)
        daesangs = [c["name"] for c in categories if c["family"] == "Daesang"]
        assert daesangs == sorted(daesangs)
        assert {"category_id": "soty", "name": "Song of the Year", "family": "Daesang"} in categories

    def test_removed_categories_are_not_active(self):
        remove_category("soty")

        assert "soty" not in [c["category_id"] for c in get_active_hma_categories()]

    def test_current_categories_are_grouped_by_family_name(self):
        grouped = get_current_categories_by_family()

        assert list(grouped) == sorted(grouped)          # Bonsang, Daesang, Fun
        assert grouped["Daesang"] == ["Album of the Year", "Artist of the Year", "Music Video of the Year",
                                      "Song of the Year"]

    def test_retired_categories_are_not_listed_as_current(self, execute):
        execute(Database.HMAS, "UPDATE hma_categories SET is_active = 0 WHERE category_id = 'soty'")

        assert "Song of the Year" not in get_current_categories_by_family()["Daesang"]


class TestAddCategory:
    """Admins add categories, or bring back removed ones."""

    def test_a_new_category_is_added_active(self, query):
        assert add_category("best_fancam", "fun", "Best Fancam") is AddCategoryResult.ADDED

        [row] = query(Database.HMAS, "SELECT * FROM hma_categories WHERE category_id = 'best_fancam'")
        assert (row["family_id"], row["name"], row["is_active"]) == ("fun", "Best Fancam", 1)
        assert ("best_fancam", "Best Fancam") in _family("Fun")

    def test_a_removed_category_is_restored_with_the_new_name_and_family(self, query):
        remove_category("best_band")

        assert add_category("best_band", "fun", "Best Band (Fun)") is AddCategoryResult.RESTORED

        [row] = query(Database.HMAS, "SELECT * FROM hma_categories WHERE category_id = 'best_band'")
        assert (row["family_id"], row["name"], row["is_active"]) == ("fun", "Best Band (Fun)", 1)

    def test_restoring_brings_back_the_earlier_nominations(self):
        _nominate(2026, 1, ["best_band"], "DAY6")
        remove_category("best_band")

        add_category("best_band", "bonsang", "Best Band")

        assert get_yearly_export_data(2026)["Bonsang"]["Best Band"] == [(1, "DAY6")]

    def test_an_active_id_is_refused(self, query):
        assert add_category("soty", "fun", "Something else") is AddCategoryResult.ALREADY_ACTIVE

        assert query(Database.HMAS, "SELECT name FROM hma_categories WHERE category_id = 'soty'")[0]["name"] == \
            "Song of the Year"

    def test_an_active_name_is_refused_whatever_its_case(self):
        assert add_category("soty2", "fun", "song of the YEAR") is AddCategoryResult.NAME_TAKEN

    def test_a_removed_categorys_name_can_be_reused(self):
        remove_category("soty")

        assert add_category("song", "daesang", "Song of the Year") is AddCategoryResult.ADDED

    def test_a_full_family_is_refused(self):
        free = MAX_CATEGORIES_PER_FAMILY - len(_family("Fun"))
        for i in range(free):
            assert add_category(f"fun_{i}", "fun", f"Fun {i}") is AddCategoryResult.ADDED

        assert add_category("one_more", "fun", "One more") is AddCategoryResult.FAMILY_FULL
        assert len(_family("Fun")) == MAX_CATEGORIES_PER_FAMILY

    def test_an_unknown_family_is_rejected_by_the_database(self):
        with pytest.raises(sqlite3.IntegrityError):
            add_category("x", "not_a_family", "X")


class TestRemoveCategory:
    """Removing a category hides it but keeps its data."""

    def test_removing_hides_it_from_the_nomination_menus(self, query):
        assert remove_category("soty") is RemoveCategoryResult.REMOVED

        assert "soty" not in [category_id for category_id, _ in _family("Daesang")]
        assert query(Database.HMAS, "SELECT is_active FROM hma_categories WHERE category_id = 'soty'")[0][0] == 0

    def test_the_nominations_finalists_and_votes_are_kept(self, query):
        _nominate(2026, 1, ["soty"], "IVE - HEYA")
        set_final_nominees(2026, "soty", ["A", "B", "C"])
        save_hma_vote(2026, 1, "soty", "A", "B", "C")

        remove_category("soty")

        assert len(query(Database.HMAS, "SELECT * FROM hma_nominations")) == 1
        assert get_hma_final_nominees(2026, "soty") == ["A", "B", "C"]
        assert get_user_hma_votes(2026, 1)["soty"]["first_choice"] == "A"

    def test_removing_twice_says_so(self):
        remove_category("soty")

        assert remove_category("soty") is RemoveCategoryResult.ALREADY_REMOVED

    def test_an_unknown_category(self):
        assert remove_category("not_a_category") is RemoveCategoryResult.NO_SUCH_CATEGORY

    def test_a_removed_category_cannot_get_finalists(self):
        remove_category("soty")

        assert set_final_nominees(2026, "soty", ["A", "B", "C"]) is False
        assert get_hma_final_nominees(2026, "soty") == []


class TestBallots:
    """get_hma_ballots reads back every ballot for counting."""

    def test_no_votes(self):
        assert not get_hma_ballots(2026)

    def test_ballots_are_grouped_by_category_for_the_year(self):
        save_hma_vote(2026, 1, "soty", "A", "B", "C")
        save_hma_vote(2026, 2, "soty", "B", "A", "C")
        save_hma_vote(2026, 1, "aoty", "X", "Y", "Z")
        save_hma_vote(2025, 1, "soty", "Old", "Older", "Oldest")

        ballots = get_hma_ballots(2026)

        assert sorted(ballots["soty"]) == [("A", "B", "C"), ("B", "A", "C")]
        assert ballots["aoty"] == [("X", "Y", "Z")]
