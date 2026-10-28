"""Tests for commands/hmas.py: adding and removing HMA categories, and picking one as you type."""

import pytest
from discord import app_commands

from commands.hmas import (
    CATEGORY_ID_PATTERN, FAMILY_CHOICES, active_category_autocomplete, add_hma_category, remove_hma_category
)
from config import Database
from db.hmas import MAX_CATEGORIES_PER_FAMILY, get_active_hma_categories, remove_category

DAESANG, BONSANG, FUN = FAMILY_CHOICES


@pytest.fixture(autouse=True)
def _hmas_database(databases):
    databases(Database.HMAS)


def _active_ids():
    return {c["category_id"] for c in get_active_hma_categories()}


def _family(display_name):
    return [(c["category_id"], c["name"]) for c in get_active_hma_categories() if c["family"] == display_name]


class TestAddCategory:
    """/add-hma-category adds a category to a family, or restores a removed one."""

    async def test_adds_it_and_says_what_to_do_next(self, admin_interaction):
        await add_hma_category.callback(admin_interaction, "best_fancam", FUN, "Best Fancam")

        assert ("best_fancam", "Best Fancam") in _family("Fun")
        [reply] = admin_interaction.sent
        assert reply.ephemeral
        assert reply.content.startswith("✅ Added **Best Fancam** (`best_fancam`) to the Fun awards.")
        assert "`/hma-set-nominees`" in reply.content

    async def test_the_id_is_tidied_and_the_name_trimmed(self, admin_interaction):
        await add_hma_category.callback(admin_interaction, "  Best_Fancam ", FUN, "  Best Fancam  ")

        assert ("best_fancam", "Best Fancam") in _family("Fun")

    @pytest.mark.parametrize("category_id", ["best fancam", "best-fancam", "émoji", "x" * 31, ""])
    async def test_an_id_that_is_not_short_lowercase_and_plain_is_refused(self, admin_interaction, category_id):
        before = _active_ids()

        await add_hma_category.callback(admin_interaction, category_id, FUN, "Best Fancam")

        assert admin_interaction.sent[0].content.startswith("❌ A category ID can only use lowercase letters")
        assert _active_ids() == before

    def test_the_id_pattern_accepts_the_seeded_ids(self):
        assert all(CATEGORY_ID_PATTERN.fullmatch(category_id) for category_id in _active_ids())

    async def test_a_removed_category_is_restored(self, admin_interaction):
        remove_category("best_band")

        await add_hma_category.callback(admin_interaction, "best_band", BONSANG, "Best Band")

        assert "best_band" in _active_ids()
        assert admin_interaction.sent[0].content.startswith("✅ Brought back `best_band` as **Best Band**")

    @pytest.mark.parametrize("category_id, name, message", [
        ("soty", "Something new", "❌ There is already an active category with the ID `soty`."),
        ("soty2", "Song of the Year", "❌ There is already an active category called **Song of the Year**."),
    ])
    async def test_a_duplicate_is_refused(self, admin_interaction, category_id, name, message):
        await add_hma_category.callback(admin_interaction, category_id, DAESANG, name)

        [reply] = admin_interaction.sent
        assert reply.content == message
        assert "`/hma-set-nominees`" not in reply.content

    async def test_a_full_family_is_refused(self, admin_interaction):
        for i in range(MAX_CATEGORIES_PER_FAMILY - len(_family("Fun"))):
            await add_hma_category.callback(admin_interaction, f"fun_{i}", FUN, f"Fun {i}")

        await add_hma_category.callback(admin_interaction, "one_more", FUN, "One more")

        assert admin_interaction.sent[-1].content.startswith("❌ The Fun awards already have 25 categories")
        assert "one_more" not in _active_ids()

    def test_the_family_is_picked_from_a_list(self):
        family = next(p for p in add_hma_category.parameters if p.name == "family")

        assert [c.value for c in family.choices] == ["daesang", "bonsang", "fun"]

    def test_the_name_fits_a_nomination_box_title(self):
        name = next(p for p in add_hma_category.parameters if p.name == "name")

        assert (name.min_value, name.max_value) == (1, 45)


class TestRemoveCategory:
    """/remove-hma-category takes a category out of the awards, keeping its data."""

    async def test_removes_it_and_explains_how_to_bring_it_back(self, admin_interaction):
        await remove_hma_category.callback(admin_interaction, "best_band")

        assert "best_band" not in _active_ids()
        [reply] = admin_interaction.sent
        assert reply.ephemeral
        assert reply.content.startswith("✅ Removed `best_band`.")
        assert "`/add-hma-category` with the same ID brings it back" in reply.content

    async def test_removing_twice_changes_nothing(self, admin_interaction):
        remove_category("best_band")

        await remove_hma_category.callback(admin_interaction, "best_band")

        assert admin_interaction.sent[0].content == "`best_band` was already removed, so nothing changed."

    async def test_an_unknown_category(self, admin_interaction):
        await remove_hma_category.callback(admin_interaction, "nope")

        assert admin_interaction.sent[0].content == "❌ There is no category called `nope`."


class TestCategoryAutocomplete:
    """Commands that take a category suggest the active ones as the admin types."""

    async def test_matches_the_name_or_the_id_ignoring_case(self, admin_interaction):
        by_name = await active_category_autocomplete(admin_interaction, "song OF")
        by_id = await active_category_autocomplete(admin_interaction, "SOTY")

        assert by_name == by_id == [app_commands.Choice(name="Song of the Year (soty)", value="soty")]

    async def test_removed_categories_are_not_suggested(self, admin_interaction):
        remove_category("soty")

        assert await active_category_autocomplete(admin_interaction, "soty") == []

    async def test_nothing_typed_suggests_at_most_25(self, admin_interaction):
        choices = await active_category_autocomplete(admin_interaction, "")

        assert len(choices) == 25 < len(_active_ids())
        assert choices[0].value in {"aoty", "aroty", "mvoty", "soty"}           # Daesangs first

    async def test_a_long_name_is_cut_to_what_discord_shows(self, admin_interaction, execute):
        execute(Database.HMAS, "INSERT INTO hma_categories (category_id, family_id, name) VALUES ('long', 'fun', ?)",
                "x" * 100)

        [choice] = await active_category_autocomplete(admin_interaction, "long")

        assert len(choice.name) == 100 and choice.value == "long"
