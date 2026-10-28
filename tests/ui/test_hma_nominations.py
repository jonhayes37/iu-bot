"""Tests for ui/hma_nominations.py: the pages of HMA nominations, the private menu and the forms."""

import sqlite3
from unittest import mock

import discord
import pytest

from config import Database
from db.bot import close_end_of_year
from db.hmas import add_category, get_active_hma_categories, get_user_nominations, replace_user_nominations
from ui.base import DATABASE_ERROR
from ui.hma_nominations import (
    HMANominationsButton, NominationMenuView, NominationPage, NominationPageButton, NominationPageModal,
    menu_text, nomination_pages, parse_nominees
)
from testsupport.ui import button_labels, fill, match_custom_id

VIDEO = "https://youtu.be/dQw4w9WgXcQ"


@pytest.fixture(autouse=True)
def _databases(databases, frozen_time):
    databases(Database.HMAS, Database.BOT)
    frozen_time("2026-11-25 12:00:00")


def _pages():
    return nomination_pages(get_active_hma_categories())


def _page(label):
    return next(page for page in _pages() if page.label == label)


def _modal(label, nominations=None):
    return NominationPageModal(2026, _page(label), len(_pages()), nominations or {})


def _box(modal, category_id):
    return modal.boxes[category_id]


async def _save(interaction, label, **typed):
    """Types into a page's boxes (by category ID) and submits it."""
    modal = _modal(label, get_user_nominations(2026, interaction.user.id))
    for category_id, text in typed.items():
        fill(_box(modal, category_id), text)
    await modal.on_submit(interaction)
    return modal


class TestPages:
    """Each family gets its own pages, filled to 5 categories before the next one starts."""

    def test_the_seeded_categories_make_seven_pages(self):
        pages = _pages()

        assert [page.label for page in pages] == ["Daesang", "Bonsang 1/4", "Bonsang 2/4", "Bonsang 3/4",
                                                  "Bonsang 4/4", "Fun 1/2", "Fun 2/2"]
        assert [len(page.categories) for page in pages] == [4, 5, 5, 5, 2, 5, 1]
        assert [page.number for page in pages] == [1, 2, 3, 4, 5, 6, 7]

    def test_categories_are_alphabetical_within_a_family(self):
        bonsang = [name for page in _pages() if page.family == "Bonsang" for _, name in page.categories]

        assert bonsang == sorted(bonsang)
        assert _page("Daesang").category_ids == ["aoty", "aroty", "mvoty", "soty"]

    def test_a_family_of_exactly_five_fits_one_page(self):
        categories = [{"category_id": f"c{i}", "name": f"C{i}", "family": "Fun"} for i in range(5)]

        assert [(page.label, len(page.categories)) for page in nomination_pages(categories)] == [("Fun", 5)]

    def test_adding_a_category_reflows_the_pages(self):
        add_category("best_fancam", "fun", "Best Fancam")

        assert [len(page.categories) for page in _pages() if page.family == "Fun"] == [5, 2]

    def test_no_categories_no_pages(self):
        assert not nomination_pages([])


class TestParseNominees:
    """One nominee per line, tidied."""

    def test_one_per_line_without_blanks_or_spaces(self):
        assert parse_nominees("  IVE - HEYA \n\n aespa - Supernova\n   \n") == ["IVE - HEYA", "aespa - Supernova"]

    def test_list_markers_are_removed(self):
        assert parse_nominees("1. IVE\n2) aespa\n- NewJeans\n• IU\n* BTS") == ["IVE", "aespa", "NewJeans", "IU", "BTS"]

    def test_names_that_start_with_a_number_are_kept(self):
        assert parse_nominees("2NE1\n10CM\n4MINUTE") == ["2NE1", "10CM", "4MINUTE"]

    def test_repeats_are_dropped_ignoring_case_keeping_the_first(self):
        assert parse_nominees("IVE\nive\n1. IVE\naespa") == ["IVE", "aespa"]

    def test_nothing_typed(self):
        assert not parse_nominees("")


class TestMenuText:
    """The private menu says what each page holds and how far along it is."""

    def test_first_time_every_page_lists_its_categories(self):
        text = menu_text(2026, _pages(), {})

        assert text.startswith("🏆 **2026 HMA Nominations**\nOpen a page, type your nominees (one per line)")
        assert ("⏰ **Daesang**: Album of the Year · Artist of the Year · Music Video of the Year · Song of the Year"
                in text)
        assert text.count("⏰") == 7

    def test_pages_with_nominations_show_how_many(self):
        text = menu_text(2026, _pages(), {"soty": ["A", "B"], "aoty": ["C"], "best_band": ["DAY6"]})

        assert "✅ **Daesang**: 3 nominations" in text
        assert "✅ **Bonsang 1/4**: 1 nomination" in text
        assert text.count("⏰") == 5

    def test_a_note_goes_first(self):
        assert menu_text(2026, _pages(), {}, note="✅ Saved").startswith("✅ Saved\n\n🏆 **2026 HMA Nominations**")


class TestMenuView:
    """A row of buttons per family; filled pages are ticked and the next page is green."""

    async def test_a_button_per_page_on_a_row_per_family(self):
        view = NominationMenuView(2026, _pages(), {}, next_page=1)

        assert button_labels(view) == ["Daesang", "Bonsang 1/4", "Bonsang 2/4", "Bonsang 3/4", "Bonsang 4/4",
                                       "Fun 1/2", "Fun 2/2"]
        assert [button.item.row for button in view.children] == [0, 1, 1, 1, 1, 2, 2]
        assert [button.item.custom_id for button in view.children][:2] == ["hma_nom_page:2026:1",
                                                                           "hma_nom_page:2026:2"]
        assert view.timeout is None

    async def test_the_next_page_is_green_and_filled_pages_are_ticked(self):
        view = NominationMenuView(2026, _pages(), {"soty": ["A"]}, next_page=2)

        styles = [button.item.style for button in view.children]
        assert styles[1] is discord.ButtonStyle.success
        assert styles.count(discord.ButtonStyle.success) == 1
        assert [str(button.item.emoji) if button.item.emoji else None for button in view.children][:2] == ["✅", None]


class TestHMANominationsButton:
    """The hub's button opens the member's private menu."""

    async def test_the_button_carries_the_year(self, interaction):
        button = HMANominationsButton(2026)
        rebuilt = await HMANominationsButton.from_custom_id(
            interaction, mock.Mock(), match_custom_id(HMANominationsButton, "btn_nom_hma_2025"))

        assert (button.item.custom_id, button.item.label) == ("btn_nom_hma_2026", "2026 HMA Nominations")
        assert rebuilt.year == 2025

    async def test_opens_the_menu_privately_with_the_first_page_green(self, interaction):
        await HMANominationsButton(2026).callback(interaction)

        [reply] = interaction.sent
        assert reply.ephemeral
        assert reply.content.startswith("🏆 **2026 HMA Nominations**")
        view = reply.kwargs["view"]
        assert view.children[0].item.style is discord.ButtonStyle.success

    async def test_the_first_empty_page_is_green_for_someone_part_way(self, interaction):
        replace_user_nominations(2026, interaction.user.id, {"soty": ["IVE - HEYA"]})

        await HMANominationsButton(2026).callback(interaction)

        view = interaction.sent[0].kwargs["view"]
        assert [button.item.label for button in view.children
                if button.item.style is discord.ButtonStyle.success] == ["Bonsang 1/4"]

    async def test_with_no_categories_it_says_so(self, interaction, execute):
        execute(Database.HMAS, "UPDATE hma_categories SET is_active = 0")

        await HMANominationsButton(2026).callback(interaction)

        [reply] = interaction.sent
        assert reply.content == "There are no HMA categories yet, so there's nothing to nominate for."
        assert "view" not in reply.kwargs

    async def test_a_database_failure_is_reported(self, interaction, execute):
        execute(Database.HMAS, "DROP TABLE hma_nominations")

        await HMANominationsButton(2026).callback(interaction)

        assert interaction.sent[0].content == DATABASE_ERROR


class TestNominationPageButton:
    """A menu button opens its page's form, filled in with what was saved."""

    async def test_rebuilt_with_its_year_and_page_after_a_restart(self, interaction):
        rebuilt = await NominationPageButton.from_custom_id(
            interaction, mock.Mock(), match_custom_id(NominationPageButton, "hma_nom_page:2026:3"))

        assert (rebuilt.year, rebuilt.page) == (2026, 3)

    async def test_opens_the_pages_form_with_earlier_nominations(self, interaction):
        replace_user_nominations(2026, interaction.user.id, {"soty": ["IVE - HEYA", "aespa - Supernova"]})

        await NominationPageButton(2026, 1).callback(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, NominationPageModal)
        assert modal.page.label == "Daesang"
        assert _box(modal, "soty").default == "IVE - HEYA\naespa - Supernova"
        assert _box(modal, "aoty").default is None

    async def test_a_page_that_no_longer_exists(self, interaction):
        await NominationPageButton(2026, 9).callback(interaction)

        assert interaction.sent[0].content.startswith("The categories have changed since this menu was opened.")
        interaction.response.send_modal.assert_not_awaited()


class TestPageForm:
    """A page's form: a box per category."""

    async def test_titled_with_the_page_and_a_labelled_box_per_category(self):
        modal = _modal("Bonsang 2/4")

        assert modal.title == "Bonsang 2/4 nominations (3 of 7)"
        labels = [(label.text, label.description) for label in modal.children]
        assert labels[0] == ("Best Dance Cover", "One per line, each with its YouTube link. Leave blank to skip.")
        assert labels[1] == ("Best Female Rookie", "One nominee per line. Leave blank to skip.")
        box = _box(modal, "best_dance_cover")
        assert (box.required, box.max_length, box.style) == (False, 1000, discord.TextStyle.paragraph)

    async def test_saving_stores_every_box_and_updates_the_menu(self, interaction):
        await _save(interaction, "Daesang", soty="1. IVE - HEYA\n2. aespa - Supernova\n\nive - heya", aoty="IU")

        assert get_user_nominations(2026, interaction.user.id) == {"soty": ["IVE - HEYA", "aespa - Supernova"],
                                                                   "aoty": ["IU"]}
        [reply] = interaction.sent
        assert reply.via == "edit"
        assert reply.content.startswith("✅ Saved **Daesang**: 3 nominations in 2 categories.\n\n🏆")
        assert "✅ **Daesang**: 3 nominations" in reply.content
        greens = [b.item.label for b in reply.kwargs["view"].children if b.item.style is discord.ButtonStyle.success]
        assert greens == ["Bonsang 1/4"]

    async def test_one_nomination_in_one_category_reads_naturally(self, interaction):
        await _save(interaction, "Daesang", soty="IVE - HEYA")

        assert interaction.sent[0].content.startswith("✅ Saved **Daesang**: 1 nomination in 1 category.")

    async def test_emptying_a_box_removes_those_nominations(self, interaction):
        replace_user_nominations(2026, interaction.user.id, {"soty": ["IVE - HEYA"], "aoty": ["IU"]})

        await _save(interaction, "Daesang", soty="")

        assert get_user_nominations(2026, interaction.user.id) == {"aoty": ["IU"]}

    async def test_other_pages_are_left_alone(self, interaction):
        replace_user_nominations(2026, interaction.user.id, {"best_band": ["DAY6"]})

        await _save(interaction, "Daesang", soty="IVE - HEYA")

        assert get_user_nominations(2026, interaction.user.id)["best_band"] == ["DAY6"]

    async def test_the_next_green_page_wraps_round_to_an_earlier_empty_one(self, interaction):
        await _save(interaction, "Fun 2/2", unique_mv="aespa - Supernova")

        greens = [b.item.label for b in interaction.sent[0].kwargs["view"].children
                  if b.item.style is discord.ButtonStyle.success]
        assert greens == ["Daesang"]

    async def test_when_every_page_has_nominations_nothing_is_green(self, interaction):
        replace_user_nominations(2026, interaction.user.id, {
            page.category_ids[0]: ["x"] for page in _pages() if page.label != "Fun 2/2"})

        await _save(interaction, "Fun 2/2", unique_mv="aespa - Supernova")

        styles = {b.item.style for b in interaction.sent[0].kwargs["view"].children}
        assert styles == {discord.ButtonStyle.secondary}

    async def test_cover_nominees_without_a_link_are_not_saved_and_listed(self, interaction):
        await _save(interaction, "Bonsang 2/4",
                    best_dance_cover=f"Great cover {VIDEO}\nmy favourite NewJeans cover", best_gg="IVE")

        assert get_user_nominations(2026, interaction.user.id) == {
            "best_dance_cover": [f"Great cover {VIDEO}"], "best_gg": ["IVE"]}
        content = interaction.sent[0].content
        assert content.startswith("✅ Saved **Bonsang 2/4**: 2 nominations in 2 categories.\n"
                                  "⚠️ Not saved (fix these and save the page again):\n"
                                  "• Best Dance Cover needs a YouTube link: my favourite NewJeans cover")

    async def test_a_nominee_that_is_too_long_is_not_saved(self, interaction):
        await _save(interaction, "Daesang", soty="x" * 301 + "\nIVE - HEYA")

        assert get_user_nominations(2026, interaction.user.id) == {"soty": ["IVE - HEYA"]}
        assert "• Song of the Year: too long (301 characters, at most 300): " in interaction.sent[0].content

    async def test_a_long_list_of_problems_is_summarised(self, interaction):
        await _save(interaction, "Bonsang 4/4", best_vocal_cover="\n".join(f"cover {i}" for i in range(12)))

        content = interaction.sent[0].content
        assert content.count("needs a YouTube link") == 8
        assert "…and 4 more" in content

    async def test_once_the_year_is_closed_nothing_is_saved(self, interaction):
        close_end_of_year(2026)

        await _save(interaction, "Daesang", soty="IVE - HEYA")

        assert not get_user_nominations(2026, interaction.user.id)
        assert interaction.sent[0].content.startswith("🔒 The 2026 end of year festivities are closed")

    async def test_a_failed_save_hands_every_box_back(self, interaction):
        modal = _modal("Daesang")
        fill(_box(modal, "soty"), "IVE - HEYA")

        await modal.on_error(interaction, sqlite3.Error("x"))

        [reply] = interaction.sent
        assert reply.content.startswith(DATABASE_ERROR)
        assert [(f.filename, f.fp.read()) for f in reply.kwargs["files"]] == [("soty.txt", b"IVE - HEYA")]


def test_a_page_label_without_parts_is_just_the_family():
    assert NominationPage(1, "Daesang", 1, 1, (("soty", "Song of the Year"),)).label == "Daesang"
