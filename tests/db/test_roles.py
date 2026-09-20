"""Tests for db/roles.py"""

import threading

import pytest

from config import Database
from db.roles import (
    AliasClash, get_all_roles_grouped, get_display_message_ids, get_role_id, register_new_role,
    replace_display_message_ids
)


@pytest.fixture(autouse=True)
def _roles_database(databases):
    databases(Database.ROLES)


class TestRegisterNewRole:
    """register_new_role stores a role, its category and its aliases."""

    def test_creates_the_category_role_and_aliases(self, query):
        register_new_role(100, "Girl Groups", "Music", ["gg", "girlgroups"])

        assert [row["name"] for row in query(Database.ROLES, "SELECT name FROM role_categories")] == ["Music"]
        role = query(Database.ROLES, "SELECT role_id, role_name FROM assignable_roles")[0]
        assert (role["role_id"], role["role_name"]) == (100, "Girl Groups")
        aliases = {row["alias"] for row in query(Database.ROLES, "SELECT alias FROM role_aliases")}
        assert aliases == {"gg", "girlgroups", "girl groups"}

    def test_the_lowercased_role_name_is_always_an_alias(self, query):
        register_new_role(100, "Watch Parties", "Events", [])

        assert [row["alias"] for row in query(Database.ROLES, "SELECT alias FROM role_aliases")] == ["watch parties"]

    def test_aliases_are_trimmed_lowercased_and_deduplicated(self, query):
        register_new_role(100, "Trivia", "Events", ["  Quiz ", "QUIZ", "quiz", "", "   "])

        aliases = {row["alias"] for row in query(Database.ROLES, "SELECT alias FROM role_aliases")}
        assert aliases == {"quiz", "trivia"}

    def test_a_second_role_reuses_the_category(self, query):
        register_new_role(100, "A", "Music", [])
        register_new_role(101, "B", "Music", [])

        assert len(query(Database.ROLES, "SELECT * FROM role_categories")) == 1
        assert len(query(Database.ROLES, "SELECT * FROM assignable_roles")) == 2

    def test_registering_again_updates_the_role_and_keeps_its_aliases(self, query):
        # An INSERT OR REPLACE would delete the role first and cascade away its aliases
        register_new_role(100, "Old Name", "Music", ["keepme"])

        register_new_role(100, "New Name", "Events", ["extra"])

        assert query(Database.ROLES, "SELECT role_name FROM assignable_roles WHERE role_id = 100")[0][0] == "New Name"
        aliases = {row["alias"] for row in query(Database.ROLES, "SELECT alias FROM role_aliases")}
        assert aliases == {"keepme", "extra", "old name", "new name"}

    def test_a_successful_registration_returns_no_clashes(self):
        assert register_new_role(100, "Girl Groups", "Music", ["gg"]) == []


class TestAliasClashes:
    """A name can only belong to one role, or get_role_id couldn't tell which one is meant."""

    @pytest.fixture(autouse=True)
    def _existing_role(self):
        register_new_role(100, "Girl Groups", "Music", ["gg", "girls"])

    def test_an_alias_used_by_another_role_is_reported(self):
        clashes = register_new_role(101, "Rookies", "Music", ["gg"])

        assert clashes == [AliasClash(alias="gg", role_id=100, role_name="Girl Groups")]

    def test_nothing_is_saved_when_there_is_a_clash(self, query):
        register_new_role(101, "Rookies", "Fresh", ["fresh", "gg"])

        assert query(Database.ROLES, "SELECT * FROM assignable_roles WHERE role_id = 101") == []
        assert query(Database.ROLES, "SELECT * FROM role_aliases WHERE role_id = 101") == []
        assert query(Database.ROLES, "SELECT * FROM role_categories WHERE name = 'Fresh'") == []

    def test_the_existing_role_keeps_the_alias(self):
        register_new_role(101, "Rookies", "Music", ["gg"])

        assert get_role_id("gg") == 100

    def test_every_clash_is_reported_at_once(self):
        clashes = register_new_role(101, "Rookies", "Music", ["girls", "gg", "new"])

        assert [(c.alias, c.role_name) for c in clashes] == [("gg", "Girl Groups"), ("girls", "Girl Groups")]

    def test_the_roles_own_name_counts_as_an_alias(self):
        # A new role literally named "GG" would answer to "gg", which already means Girl Groups
        clashes = register_new_role(101, "GG", "Music", [])

        assert clashes == [AliasClash(alias="gg", role_id=100, role_name="Girl Groups")]

    def test_an_alias_that_is_another_roles_name_is_a_clash(self):
        clashes = register_new_role(101, "Rookies", "Music", ["Girl Groups"])

        assert clashes == [AliasClash(alias="girl groups", role_id=100, role_name="Girl Groups")]

    def test_case_and_spacing_do_not_hide_a_clash(self):
        assert register_new_role(101, "Rookies", "Music", ["  GG  "])

    def test_a_role_can_be_registered_again_with_its_own_aliases(self):
        assert register_new_role(100, "Girl Groups", "Music", ["gg", "extra"]) == []

        assert get_role_id("extra") == 100

    def test_a_role_can_be_renamed_without_clashing_with_itself(self):
        assert register_new_role(100, "Girl Group Fans", "Music", ["gg"]) == []

        assert get_role_id("girl group fans") == 100

    def test_an_unrelated_alias_is_still_allowed(self):
        assert register_new_role(101, "Rookies", "Music", ["fresh"]) == []

        assert get_role_id("fresh") == 101

    def test_two_registrations_at_once_cannot_both_claim_an_alias(self):
        gate = threading.Barrier(2)
        results = []

        def register(role_id):
            gate.wait()
            results.append(register_new_role(role_id, f"Role {role_id}", "Music", ["contested"]))

        threads = [threading.Thread(target=register, args=(role_id,)) for role_id in (201, 202)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(bool(clashes) for clashes in results) == [False, True]


class TestGetRoleId:
    """get_role_id finds a role by alias or by name."""

    def test_finds_by_alias(self):
        register_new_role(100, "Girl Groups", "Music", ["gg"])

        assert get_role_id("gg") == 100

    def test_finds_by_the_role_name_in_lowercase(self):
        register_new_role(100, "Girl Groups", "Music", [])

        assert get_role_id("girl groups") == 100

    def test_unknown_is_none(self):
        register_new_role(100, "Girl Groups", "Music", [])

        assert get_role_id("boy groups") is None


class TestGetAllRolesGrouped:
    """get_all_roles_grouped builds the {category: {role: [aliases]}} tree shown in #roles."""

    def test_empty(self):
        assert not get_all_roles_grouped()

    def test_groups_roles_and_their_aliases_by_category(self):
        register_new_role(1, "Girl Groups", "Music", ["gg"])
        register_new_role(2, "Trivia", "Events", [])

        grouped = get_all_roles_grouped()

        assert grouped["Music"]["Girl Groups"] == ["gg", "girl groups"]
        assert grouped["Events"]["Trivia"] == ["trivia"]

    def test_categories_follow_display_order_then_roles_and_aliases_alphabetically(self, execute):
        register_new_role(1, "Zebra", "Later", ["z2", "z1"])
        register_new_role(2, "Apple", "Later", [])
        register_new_role(3, "Middle", "Earlier", [])
        execute(Database.ROLES, "UPDATE role_categories SET display_order = 1 WHERE name = 'Later'")
        execute(Database.ROLES, "UPDATE role_categories SET display_order = 0 WHERE name = 'Earlier'")

        grouped = get_all_roles_grouped()

        assert list(grouped) == ["Earlier", "Later"]
        assert list(grouped["Later"]) == ["Apple", "Zebra"]
        assert grouped["Later"]["Zebra"] == ["z1", "z2", "zebra"]

    def test_a_role_with_no_aliases_still_appears(self, execute):
        register_new_role(1, "Solo", "Music", [])
        execute(Database.ROLES, "DELETE FROM role_aliases")

        assert get_all_roles_grouped() == {"Music": {"Solo": []}}


class TestDisplayMessages:
    """The ids of the messages the bot keeps up to date in #roles."""

    def test_none_saved_yet(self):
        assert get_display_message_ids() == []

    def test_saves_and_reads_them_back(self):
        replace_display_message_ids([10, 20, 30])

        assert sorted(get_display_message_ids()) == [10, 20, 30]

    def test_replacing_removes_the_old_ones(self):
        replace_display_message_ids([10, 20])

        replace_display_message_ids([30])

        assert get_display_message_ids() == [30]

    def test_replacing_with_nothing_clears_them(self):
        replace_display_message_ids([10])

        replace_display_message_ids([])

        assert get_display_message_ids() == []
