"""Tests for commands/hmas.py: the HallyU Music Awards commands."""

import pytest

from commands.hmas import (
    MAX_NOMINEE_LENGTH, MAX_NOMINEES_PER_CATEGORY, end_of_year_hma_suggestions, hma_nomination,
    hma_nomination_export, hma_set_nominees, hma_suggestions_export
)
from config import Database
from db.hmas import (
    add_nominations, get_hma_final_nominees, save_category_suggestion, set_final_nominees
)
from ui.hma_nominations import MultiNominationView
from ui.hma_suggestions import HMASuggestionsHub


@pytest.fixture(autouse=True)
def _hmas_database(databases, frozen_time):
    databases(Database.HMAS)
    frozen_time("2026-10-15 12:00:00")


class TestNomination:
    """/hma-nomination starts a nomination for the member."""

    async def test_shows_the_category_picker_privately(self, interaction):
        await hma_nomination.callback(interaction, "IVE - HEYA")

        [reply] = interaction.sent
        assert reply.content == "Nominating **IVE - HEYA**\nSelect all award categories below:"
        assert reply.ephemeral
        assert isinstance(reply.kwargs["view"], MultiNominationView)
        assert reply.kwargs["view"].nominee == "IVE - HEYA"

    def test_the_nominee_text_is_limited_in_length(self):
        nominee = next(p for p in hma_nomination.parameters if p.name == "nominee")

        assert (nominee.min_value, nominee.max_value) == (1, MAX_NOMINEE_LENGTH)


class TestNominationExport:
    """/hma-nomination-export attaches every nomination for a year."""

    async def test_nothing_nominated_yet(self, admin_interaction):
        await hma_nomination_export.callback(admin_interaction)

        [reply] = admin_interaction.sent
        assert (reply.content, reply.ephemeral) == ("No nominations found for the 2026 awards yet.", True)

    async def test_attaches_the_nominations_grouped_by_family_and_category(self, admin_interaction):
        add_nominations(11, ["soty", "best_gg"], "IVE - HEYA")
        add_nominations(22, ["soty"], "aespa - Supernova")

        await hma_nomination_export.callback(admin_interaction)

        [reply] = admin_interaction.sent
        assert reply.ephemeral
        assert reply.content == "Here is the organized raw data export for the **2026 HMAs**:"
        attachment = reply.kwargs["file"]
        assert attachment.filename == "2026_hma_nominations.txt"
        text = attachment.fp.read().decode("utf-8")
        assert text.startswith("🏆 HallyU Music Awards - 2026 Nominations 🏆\n" + "=" * 50)
        assert "████ DAESANG ████" in text and "████ BONSANG ████" in text
        assert ("### Song of the Year ###\n- IVE - HEYA (Submitted by ID: 11)\n"
                "- aespa - Supernova (Submitted by ID: 22)") in text
        assert "### Best Girl Group ###\n- IVE - HEYA (Submitted by ID: 11)" in text

    async def test_another_year_can_be_asked_for(self, admin_interaction, frozen_time):
        add_nominations(11, ["soty"], "Last year's pick")
        frozen_time("2027-03-01 12:00:00")

        await hma_nomination_export.callback(admin_interaction, 2026)

        assert admin_interaction.sent[0].kwargs["file"].filename == "2026_hma_nominations.txt"

    async def test_a_year_with_nothing_says_which_year(self, admin_interaction):
        await hma_nomination_export.callback(admin_interaction, 2019)

        assert admin_interaction.sent[0].content == "No nominations found for the 2019 awards yet."


class TestSetNominees:
    """/hma-set-nominees sets the final list for a category."""

    async def test_saves_the_list_and_confirms_it(self, admin_interaction):
        await hma_set_nominees.callback(admin_interaction, "soty", "IVE - HEYA | aespa - Supernova ")

        assert get_hma_final_nominees("soty") == ["IVE - HEYA", "aespa - Supernova"]
        assert admin_interaction.sent[0].content == (
            "✅ **Saved 2 nominees for `soty` (2026)!**\n\n• IVE - HEYA\n• aespa - Supernova")

    @pytest.mark.parametrize("text", ["", "|", "  |  "])
    async def test_a_list_with_no_names_is_refused(self, admin_interaction, text):
        await hma_set_nominees.callback(admin_interaction, "soty", text)

        assert admin_interaction.sent[0].content == "❌ No valid nominees found. Check your formatting."

    async def test_more_nominees_than_a_menu_holds_are_refused(self, admin_interaction):
        many = " | ".join(f"Act {i}" for i in range(MAX_NOMINEES_PER_CATEGORY + 1))

        await hma_set_nominees.callback(admin_interaction, "soty", many)

        assert "a voting menu holds at most 25" in admin_interaction.sent[0].content
        assert get_hma_final_nominees("soty") == []

    async def test_exactly_the_most_a_menu_holds_is_fine(self, admin_interaction):
        many = " | ".join(f"Act {i}" for i in range(MAX_NOMINEES_PER_CATEGORY))

        await hma_set_nominees.callback(admin_interaction, "soty", many)

        assert len(get_hma_final_nominees("soty")) == 25

    async def test_the_same_nominee_twice_is_refused(self, admin_interaction):
        await hma_set_nominees.callback(admin_interaction, "soty", "IVE | IVE")

        assert admin_interaction.sent[0].content == "❌ The list has the same nominee more than once."

    async def test_an_unknown_category_is_refused_and_nothing_changes(self, admin_interaction):
        set_final_nominees("soty", ["Old"])

        await hma_set_nominees.callback(admin_interaction, "not_a_category", "IVE")

        assert admin_interaction.sent[0].content.startswith("❌ There is no category called `not_a_category`.")
        assert get_hma_final_nominees("soty") == ["Old"]

    async def test_the_reply_is_private(self, admin_interaction):
        await hma_set_nominees.callback(admin_interaction, "soty", "IVE")

        admin_interaction.response.defer.assert_awaited_once_with(ephemeral=True)


class TestSuggestionsHub:
    """/end-of-year-hma-suggestions posts the category suggestion hub."""

    async def test_posts_the_current_categories_and_the_hub(self, admin_interaction):
        await end_of_year_hma_suggestions.callback(admin_interaction)

        [hub] = admin_interaction.channel.sent
        assert hub.embed.title == "💡 2026 HMA Category Suggestions"
        description = hub.embed.description
        assert "**categories - not nominees** - for the 2026 HallyU Music Awards" in description
        assert "__**Current Awards:**__" in description
        assert "**Daesang**\n • Album of the Year" in description
        assert isinstance(hub.kwargs["view"], HMASuggestionsHub)
        assert admin_interaction.sent[0].content == "HMA Category Suggestions posted!"

    async def test_with_no_categories_it_says_so(self, admin_interaction, execute):
        execute(Database.HMAS, "UPDATE hma_categories SET is_active = 0")

        await end_of_year_hma_suggestions.callback(admin_interaction)

        description = admin_interaction.channel.sent[0].embed.description
        assert "*No categories currently seeded in the database.*" in description

    async def test_retired_categories_are_not_listed(self, admin_interaction, execute):
        execute(Database.HMAS, "UPDATE hma_categories SET is_active = 0 WHERE category_id = 'soty'")

        await end_of_year_hma_suggestions.callback(admin_interaction)

        assert "Song of the Year" not in admin_interaction.channel.sent[0].embed.description


class TestSuggestionsExport:
    """/hma-suggestions-export attaches the members' ideas."""

    async def test_nothing_suggested_yet(self, admin_interaction):
        await hma_suggestions_export.callback(admin_interaction)

        assert admin_interaction.sent[0].content == "No suggestions have been submitted yet."

    async def test_attaches_each_members_suggestions(self, admin_interaction):
        save_category_suggestion(1, "Jo", "Best Fancam", "Best Band")
        save_category_suggestion(2, "Sam", "Best Cover", "")
        save_category_suggestion(3, "Kit", "", "Best OST")

        await hma_suggestions_export.callback(admin_interaction)

        [reply] = admin_interaction.sent
        assert reply.content == "✅ Exported **3** community suggestions!"
        attachment = reply.kwargs["file"]
        assert attachment.filename == "2026_hma_suggestions.txt"
        text = attachment.fp.read().decode("utf-8")
        assert text.startswith("HMA CATEGORY SUGGESTIONS (2026)\n" + "=" * 40)
        assert "--- Jo ---\nADD:\nBest Fancam\n\nDROP/MERGE:\nBest Band\n" in text
        assert "--- Sam ---\nADD:\nBest Cover\n\n" in text and "DROP/MERGE:\nBest Cover" not in text
        assert "--- Kit ---\nDROP/MERGE:\nBest OST\n" in text and "ADD:\n\n" not in text
