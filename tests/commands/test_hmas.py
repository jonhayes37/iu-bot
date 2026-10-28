"""Tests for commands/hmas.py: the HallyU Music Awards commands."""

import pytest

from commands.hmas import end_of_year_hma_suggestions, hma_nomination_export, hma_set_nominees, hma_suggestions_export
from config import Database
from db.bot import EndOfYearPost, EndOfYearPostKind, close_end_of_year, get_end_of_year_posts
from db.hmas import (
    get_hma_final_nominees, remove_category, replace_user_nominations, save_category_suggestion,
    set_final_nominees
)
from ui.hma_suggestions import HMASuggestionsHub
from utils.validation import MAX_BALLOT_NOMINEES, MAX_BALLOT_NOMINEE_LENGTH


@pytest.fixture(autouse=True)
def _hmas_database(databases, frozen_time):
    databases(Database.HMAS, Database.BOT)
    frozen_time("2026-10-15 12:00:00")


class TestNominationExport:
    """/hma-nomination-export attaches every nomination for a year."""

    async def test_it_answers_privately_before_uploading_the_file(self, admin_interaction):
        # The upload can take longer than the 3 seconds Discord allows for a first response
        replace_user_nominations(2026, 11, {"soty": ["IVE - HEYA"]})
        order = []
        admin_interaction.response.defer.side_effect = lambda *a, **k: order.append(("defer", k))
        admin_interaction.followup.send.side_effect = lambda *a, **k: order.append(("upload", {}))

        await hma_nomination_export.callback(admin_interaction)

        assert order == [("defer", {"ephemeral": True}), ("upload", {})]
        admin_interaction.response.send_message.assert_not_awaited()

    async def test_nothing_nominated_yet(self, admin_interaction):
        await hma_nomination_export.callback(admin_interaction)

        [reply] = admin_interaction.sent
        assert (reply.content, reply.ephemeral) == ("No nominations found for the 2026 awards yet.", True)

    async def test_attaches_the_nominations_grouped_by_family_and_category(self, admin_interaction):
        replace_user_nominations(2026, 11, {"soty": ["IVE - HEYA"], "best_gg": ["IVE - HEYA"]})
        replace_user_nominations(2026, 22, {"soty": ["aespa - Supernova"]})

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
        replace_user_nominations(2026, 11, {"soty": ["Last year's pick"]})
        frozen_time("2027-03-01 12:00:00")

        await hma_nomination_export.callback(admin_interaction, 2026)

        assert admin_interaction.sent[0].kwargs["file"].filename == "2026_hma_nominations.txt"

    async def test_in_december_it_exports_the_year_being_celebrated(self, admin_interaction, frozen_time):
        replace_user_nominations(2026, 11, {"soty": ["IVE - HEYA"]})
        frozen_time("2026-12-02 12:00:00")

        await hma_nomination_export.callback(admin_interaction)

        assert admin_interaction.sent[0].kwargs["file"].filename == "2026_hma_nominations.txt"

    async def test_a_year_with_nothing_says_which_year(self, admin_interaction):
        await hma_nomination_export.callback(admin_interaction, 2019)

        assert admin_interaction.sent[0].content == "No nominations found for the 2019 awards yet."


class TestSetNominees:
    """/hma-set-nominees sets the final list for a category."""

    async def test_saves_the_list_and_confirms_it(self, admin_interaction):
        await hma_set_nominees.callback(admin_interaction, "soty",
                                        "IVE - HEYA | aespa - Supernova | IU - Love wins all ")

        assert get_hma_final_nominees(2026, "soty") == ["IU - Love wins all", "IVE - HEYA", "aespa - Supernova"]
        assert admin_interaction.sent[0].content == (
            "✅ **Saved 3 nominees for `soty` (2026)!**\n\n• IVE - HEYA\n• aespa - Supernova\n• IU - Love wins all")

    @pytest.mark.parametrize("text", ["", "|", "  |  "])
    async def test_a_list_with_no_names_is_refused(self, admin_interaction, text):
        await hma_set_nominees.callback(admin_interaction, "soty", text)

        assert admin_interaction.sent[0].content == "❌ No valid nominees found. Check your formatting."

    async def test_more_nominees_than_a_menu_holds_are_refused(self, admin_interaction):
        many = " | ".join(f"Act {i}" for i in range(MAX_BALLOT_NOMINEES + 1))

        await hma_set_nominees.callback(admin_interaction, "soty", many)

        assert "a voting menu holds at most 25" in admin_interaction.sent[0].content
        assert get_hma_final_nominees(2026, "soty") == []

    async def test_exactly_the_most_a_menu_holds_is_fine(self, admin_interaction):
        many = " | ".join(f"Act {i}" for i in range(MAX_BALLOT_NOMINEES))

        await hma_set_nominees.callback(admin_interaction, "soty", many)

        assert len(get_hma_final_nominees(2026, "soty")) == 25

    async def test_fewer_than_a_ballot_ranks_are_refused(self, admin_interaction):
        await hma_set_nominees.callback(admin_interaction, "soty", "IVE | aespa")

        assert admin_interaction.sent[0].content.startswith("❌ You gave 2 nominees, but voters rank their top 3")
        assert get_hma_final_nominees(2026, "soty") == []

    async def test_a_nominee_longer_than_a_menu_shows_is_refused(self, admin_interaction):
        long_name = "x" * (MAX_BALLOT_NOMINEE_LENGTH + 1)

        await hma_set_nominees.callback(admin_interaction, "soty", f"IVE | aespa | {long_name}")

        assert "at most 100 characters per nominee" in admin_interaction.sent[0].content
        assert get_hma_final_nominees(2026, "soty") == []

    async def test_the_same_nominee_twice_is_refused(self, admin_interaction):
        await hma_set_nominees.callback(admin_interaction, "soty", "IVE | aespa | IVE")

        assert admin_interaction.sent[0].content == "❌ The list has the same nominee more than once."

    async def test_an_unknown_category_is_refused_and_nothing_changes(self, admin_interaction):
        set_final_nominees(2026, "soty", ["Old"])

        await hma_set_nominees.callback(admin_interaction, "not_a_category", "IVE | aespa | IU")

        assert admin_interaction.sent[0].content.startswith("❌ There is no active category called `not_a_category`.")
        assert get_hma_final_nominees(2026, "soty") == ["Old"]

    async def test_a_removed_category_is_refused(self, admin_interaction):
        remove_category("soty")

        await hma_set_nominees.callback(admin_interaction, "soty", "IVE | aespa | IU")

        assert admin_interaction.sent[0].content.startswith("❌ There is no active category called `soty`.")
        assert get_hma_final_nominees(2026, "soty") == []

    async def test_the_reply_is_private(self, admin_interaction):
        await hma_set_nominees.callback(admin_interaction, "soty", "IVE | aespa | IU")

        admin_interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    async def test_in_december_the_finalists_are_for_the_year_being_celebrated(self, admin_interaction, frozen_time):
        frozen_time("2026-12-03 12:00:00")

        await hma_set_nominees.callback(admin_interaction, "soty", "IVE | aespa | IU")

        assert get_hma_final_nominees(2026, "soty") == ["IU", "IVE", "aespa"]
        assert "(2026)" in admin_interaction.sent[0].content


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

    async def test_the_post_is_remembered_so_it_can_be_closed(self, admin_interaction):
        await end_of_year_hma_suggestions.callback(admin_interaction)

        [post] = get_end_of_year_posts(2026)
        assert (post.kind, post.channel_id) == (EndOfYearPostKind.SUGGESTIONS, admin_interaction.channel.id)
        assert isinstance(post, EndOfYearPost)

    async def test_nothing_is_posted_once_the_year_is_closed(self, admin_interaction):
        close_end_of_year(2026)

        await end_of_year_hma_suggestions.callback(admin_interaction)

        assert admin_interaction.channel.sent == []
        assert admin_interaction.sent[0].content.startswith("🔒 The 2026 end of year festivities are closed")

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
        save_category_suggestion(2026, 1, "Jo", "Best Fancam", "Best Band")
        save_category_suggestion(2026, 2, "Sam", "Best Cover", "")
        save_category_suggestion(2026, 3, "Kit", "", "Best OST")
        save_category_suggestion(2025, 4, "Old", "Last year's idea", "")

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
        assert "--- Old ---" not in text
