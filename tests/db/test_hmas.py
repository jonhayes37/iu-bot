"""Tests for db/hmas.py: the HallyU Music Awards.

Every function that takes no year uses the current awards year (December 1 to November 30).
"""

import sqlite3

import pytest

from config import Database
from db.initialize import initialize_databases
from db.hmas import (
    add_nominations, get_all_category_suggestions, get_all_hma_categories, get_current_categories_by_family,
    get_family_choices, get_hma_final_nominees, get_user_category_suggestion, get_user_hma_votes,
    get_yearly_export_data, save_category_suggestion, save_hma_vote, set_final_nominees
)


@pytest.fixture(autouse=True)
def _hmas_database(databases, frozen_time):
    databases(Database.HMAS)
    frozen_time("2026-10-15 12:00:00")


class TestSeedData:
    """The three award families and their categories come with the schema."""

    def test_the_families_exist(self, query):
        families = {row["family_id"] for row in query(Database.HMAS, "SELECT family_id FROM hma_families")}

        assert families == {"daesang", "bonsang", "fun"}

    def test_the_daesangs_are_the_four_big_awards(self):
        names = [name for _, name in get_family_choices("daesang")]

        assert names == ["Album of the Year", "Artist of the Year", "Music Video of the Year", "Song of the Year"]

    def test_every_category_belongs_to_a_family(self, query):
        orphans = query(Database.HMAS, "SELECT * FROM hma_categories WHERE family_id NOT IN "
                                       "(SELECT family_id FROM hma_families)")

        assert orphans == []

    def test_starting_up_again_does_not_duplicate_the_seed_data(self, query):
        before = len(query(Database.HMAS, "SELECT * FROM hma_categories"))

        initialize_databases()

        assert len(query(Database.HMAS, "SELECT * FROM hma_categories")) == before

    def test_no_family_has_more_categories_than_a_dropdown_holds(self):
        # A Discord select menu shows at most 25 options
        for family in ("daesang", "bonsang", "fun"):
            assert 0 < len(get_family_choices(family)) <= 25


class TestFamilyChoices:
    """get_family_choices fills the nomination dropdowns."""

    def test_returns_id_and_name_pairs_sorted_by_name(self):
        choices = get_family_choices("daesang")

        assert choices[0] == ("aoty", "Album of the Year")
        assert [name for _, name in choices] == sorted(name for _, name in choices)

    def test_retired_categories_are_left_out(self, execute):
        execute(Database.HMAS, "UPDATE hma_categories SET is_active = 0 WHERE category_id = 'aoty'")

        assert "aoty" not in [category_id for category_id, _ in get_family_choices("daesang")]

    def test_an_unknown_family_is_empty(self):
        assert get_family_choices("nope") == []


class TestAddNominations:
    """One nominee can be put forward for several categories at once."""

    def test_saves_one_row_per_category_and_returns_the_year(self, query):
        year = add_nominations(1, ["soty", "aoty"], "IVE - HEYA")

        assert year == 2026
        rows = query(Database.HMAS, "SELECT * FROM hma_nominations ORDER BY category_id")
        assert [(r["category_id"], r["user_id"], r["nomination_text"], r["award_year"]) for r in rows] == \
            [("aoty", 1, "IVE - HEYA", 2026), ("soty", 1, "IVE - HEYA", 2026)]

    def test_a_december_nomination_counts_for_next_year(self, frozen_time):
        frozen_time("2026-12-03 12:00:00")

        assert add_nominations(1, ["soty"], "x") == 2027

    def test_an_unknown_category_saves_nothing_at_all(self, query):
        with pytest.raises(sqlite3.IntegrityError):
            add_nominations(1, ["soty", "not_a_category"], "IVE - HEYA")

        assert query(Database.HMAS, "SELECT * FROM hma_nominations") == []

    def test_the_same_person_can_nominate_several_times(self, query):
        add_nominations(1, ["soty"], "first")
        add_nominations(1, ["soty"], "second")

        assert len(query(Database.HMAS, "SELECT * FROM hma_nominations")) == 2


class TestYearlyExport:
    """get_yearly_export_data groups nominations by family then category."""

    def test_nothing_nominated(self):
        assert not get_yearly_export_data(2026)

    def test_groups_by_family_and_category_with_who_nominated(self):
        add_nominations(1, ["soty", "best_gg"], "IVE - HEYA")
        add_nominations(2, ["soty"], "aespa - Supernova")

        data = get_yearly_export_data(2026)

        assert data["Daesang"]["Song of the Year"] == [(1, "IVE - HEYA"), (2, "aespa - Supernova")]
        assert data["Bonsang"]["Best Girl Group"] == [(1, "IVE - HEYA")]

    def test_only_the_requested_year_is_returned(self, frozen_time):
        add_nominations(1, ["soty"], "this year")
        frozen_time("2027-03-01 12:00:00")
        add_nominations(2, ["soty"], "next year")

        assert get_yearly_export_data(2026)["Daesang"]["Song of the Year"] == [(1, "this year")]
        assert get_yearly_export_data(2027)["Daesang"]["Song of the Year"] == [(2, "next year")]

    def test_a_year_with_nothing_is_empty(self):
        add_nominations(1, ["soty"], "x")

        assert not get_yearly_export_data(2020)


class TestFinalNominees:
    """The vetted list for a category."""

    def test_none_yet(self):
        assert get_hma_final_nominees("soty") == []

    def test_set_returns_the_year_and_they_come_back_sorted(self):
        assert set_final_nominees("soty", ["IVE - HEYA", "aespa - Supernova", "BTS - Dynamite"]) == 2026

        assert get_hma_final_nominees("soty") == ["BTS - Dynamite", "IVE - HEYA", "aespa - Supernova"]

    def test_setting_again_replaces_the_list(self):
        set_final_nominees("soty", ["A", "B"])

        set_final_nominees("soty", ["C"])

        assert get_hma_final_nominees("soty") == ["C"]

    def test_categories_are_independent(self):
        set_final_nominees("soty", ["A"])
        set_final_nominees("aoty", ["B"])

        assert get_hma_final_nominees("soty") == ["A"]
        assert get_hma_final_nominees("aoty") == ["B"]

    def test_only_the_current_year_is_replaced(self, frozen_time):
        set_final_nominees("soty", ["this year"])
        frozen_time("2027-03-01 12:00:00")
        set_final_nominees("soty", ["next year"])
        frozen_time("2026-10-15 12:00:00")

        assert get_hma_final_nominees("soty") == ["this year"]

    def test_an_unknown_category_returns_none_and_changes_nothing(self, query):
        assert set_final_nominees("not_a_category", ["A"]) is None

        assert query(Database.HMAS, "SELECT * FROM hma_final_nominees") == []

    def test_an_unknown_category_does_not_wipe_anything_else(self):
        set_final_nominees("soty", ["A"])

        set_final_nominees("not_a_category", ["B"])

        assert get_hma_final_nominees("soty") == ["A"]

    def test_an_empty_list_clears_the_category(self):
        set_final_nominees("soty", ["A"])

        set_final_nominees("soty", [])

        assert get_hma_final_nominees("soty") == []


class TestVotes:
    """A ranked ballot of three per member per category."""

    def test_no_votes_yet(self):
        assert get_user_hma_votes(1) == {}

    def test_votes_are_keyed_by_category(self):
        save_hma_vote(1, "soty", "A", "B", "C")
        save_hma_vote(1, "aoty", "D", "E", "F")

        votes = get_user_hma_votes(1)

        assert set(votes) == {"soty", "aoty"}
        assert votes["soty"] == {"category_id": "soty", "first_choice": "A", "second_choice": "B", "third_choice": "C"}

    def test_voting_again_in_a_category_replaces_the_ballot(self, query):
        save_hma_vote(1, "soty", "A", "B", "C")

        save_hma_vote(1, "soty", "C", "B", "A")

        assert get_user_hma_votes(1)["soty"]["first_choice"] == "C"
        assert len(query(Database.HMAS, "SELECT * FROM hma_votes")) == 1

    def test_votes_are_per_member(self):
        save_hma_vote(1, "soty", "A", "B", "C")

        assert get_user_hma_votes(2) == {}

    def test_last_years_votes_are_not_this_years(self, frozen_time):
        save_hma_vote(1, "soty", "A", "B", "C")
        frozen_time("2027-03-01 12:00:00")

        assert get_user_hma_votes(1) == {}


class TestCategorySuggestions:
    """Members suggest categories to add or drop."""

    def test_none_yet(self):
        assert get_user_category_suggestion(1) is None
        assert get_all_category_suggestions() == []

    def test_save_returns_the_year_and_can_be_read_back(self):
        assert save_category_suggestion(1, "jo", "Best Fancam", "Best Band") == 2026

        assert get_user_category_suggestion(1) == {"new_categories": "Best Fancam", "dropped_categories": "Best Band"}

    def test_suggesting_again_replaces_the_earlier_one(self):
        save_category_suggestion(1, "jo", "first", "")

        save_category_suggestion(1, "jo", "second", "")

        assert get_user_category_suggestion(1)["new_categories"] == "second"
        assert len(get_all_category_suggestions()) == 1

    def test_export_lists_this_years_suggestions(self, frozen_time):
        save_category_suggestion(1, "old", "x", "y")
        frozen_time("2027-03-01 12:00:00")
        save_category_suggestion(2, "a", "x", "y")
        save_category_suggestion(3, "b", "x", "y")

        assert sorted(row["username"] for row in get_all_category_suggestions()) == ["a", "b"]

    def test_either_field_can_be_empty(self):
        save_category_suggestion(1, "jo", None, None)

        assert get_user_category_suggestion(1) == {"new_categories": None, "dropped_categories": None}


class TestCategoryLists:
    """The lists of categories shown to admins and in the suggestions post."""

    def test_all_categories_are_sorted_by_name(self):
        categories = get_all_hma_categories()

        assert [c["name"] for c in categories] == sorted(c["name"] for c in categories)
        assert {"category_id": "soty", "name": "Song of the Year"} in categories

    def test_current_categories_are_grouped_by_family_name(self):
        grouped = get_current_categories_by_family()

        assert list(grouped) == sorted(grouped)          # Bonsang, Daesang, Fun
        assert grouped["Daesang"] == ["Album of the Year", "Artist of the Year", "Music Video of the Year",
                                      "Song of the Year"]

    def test_retired_categories_are_not_listed_as_current(self, execute):
        execute(Database.HMAS, "UPDATE hma_categories SET is_active = 0 WHERE category_id = 'soty'")

        assert "Song of the Year" not in get_current_categories_by_family()["Daesang"]
        assert {"category_id": "soty", "name": "Song of the Year"} in get_all_hma_categories()
