"""Tests for ui/hma_suggestions.py: suggesting HMA categories to add or drop."""

import sqlite3
from unittest import mock

import pytest

from config import Database
from db.hmas import get_all_category_suggestions, get_user_category_suggestion, save_category_suggestion
from ui.base import DATABASE_ERROR
from ui.hma_suggestions import HMACategorySuggestionModal, HMASuggestButton, HMASuggestionsHub
from testsupport.ui import button_labels, fill, match_custom_id


@pytest.fixture(autouse=True)
def _hmas_database(databases, frozen_time):
    databases(Database.HMAS)
    frozen_time("2026-10-15 12:00:00")


async def _submit(interaction, new="", drop=""):
    modal = HMACategorySuggestionModal(2026)
    fill(modal.new_cats, new)
    fill(modal.drop_cats, drop)
    await modal.on_submit(interaction)


class TestSuggestionModal:
    """The form for category suggestions."""

    async def test_the_form_is_titled_for_the_year_and_both_boxes_are_optional(self):
        modal = HMACategorySuggestionModal(2026)

        assert modal.title == "2026 HMA Category Suggestions"
        assert (modal.new_cats.required, modal.drop_cats.required) == (False, False)
        assert (modal.new_cats.default, modal.drop_cats.default) == (None, None)

    async def test_an_earlier_suggestion_fills_the_boxes(self):
        modal = HMACategorySuggestionModal(2026, {"new_categories": "Best Fancam", "dropped_categories": "Best Band"})

        assert (modal.new_cats.default, modal.drop_cats.default) == ("Best Fancam", "Best Band")

    async def test_a_suggestion_is_saved_trimmed_and_confirmed(self, interaction):
        await _submit(interaction, new="  Best Fancam \n", drop="Best Band")

        assert get_user_category_suggestion(interaction.user.id) == {
            "new_categories": "Best Fancam", "dropped_categories": "Best Band"}
        [reply] = interaction.sent
        assert reply.content.startswith("✅ **Suggestions submitted!**")
        assert reply.ephemeral

    async def test_one_box_is_enough(self, interaction):
        await _submit(interaction, new="Best Fancam")

        assert get_user_category_suggestion(interaction.user.id)["dropped_categories"] == ""

    async def test_two_blank_boxes_are_refused(self, interaction):
        await _submit(interaction, new="   ", drop="\n")

        [reply] = interaction.sent
        assert reply.content == "❌ You left both fields blank! Please suggest at least one addition or removal."
        assert get_all_category_suggestions() == []

    async def test_suggesting_again_replaces_the_earlier_one(self, interaction):
        await _submit(interaction, new="first")
        await _submit(interaction, new="second")

        assert len(get_all_category_suggestions()) == 1
        assert get_user_category_suggestion(interaction.user.id)["new_categories"] == "second"

    async def test_a_failed_save_hands_both_boxes_back(self, interaction):
        modal = HMACategorySuggestionModal(2026)
        fill(modal.new_cats, "Best Fancam")
        fill(modal.drop_cats, "")

        await modal.on_error(interaction, sqlite3.Error("x"))

        [reply] = interaction.sent
        assert reply.content.startswith(DATABASE_ERROR)
        assert [(f.filename, f.fp.read()) for f in reply.kwargs["files"]] == [("new_categories.txt", b"Best Fancam")]


class TestSuggestButton:
    """The hub's button carries the year."""

    async def test_the_button(self):
        button = HMASuggestButton(2026)

        assert (button.item.custom_id, button.item.label) == ("btn_hma_suggest_2026", "Suggest Category Changes")

    async def test_the_button_is_rebuilt_with_its_year_after_a_restart(self, interaction):
        match = match_custom_id(HMASuggestButton, "btn_hma_suggest_2025")

        assert (await HMASuggestButton.from_custom_id(interaction, mock.Mock(), match)).year == 2025

    async def test_it_opens_an_empty_form_for_someone_new(self, interaction):
        await HMASuggestButton(2026).callback(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, HMACategorySuggestionModal)
        assert (modal.year, modal.new_cats.default) == (2026, None)

    async def test_it_prefills_an_earlier_suggestion(self, interaction):
        save_category_suggestion(interaction.user.id, "jo", "Best Fancam", "Best Band")

        await HMASuggestButton(2026).callback(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        assert (modal.new_cats.default, modal.drop_cats.default) == ("Best Fancam", "Best Band")

    async def test_a_database_failure_is_reported(self, interaction, execute):
        execute(Database.HMAS, "DROP TABLE hma_category_suggestions")

        await HMASuggestButton(2026).callback(interaction)

        assert interaction.sent[0].content == DATABASE_ERROR


async def test_the_hub_holds_the_button_and_never_times_out():
    hub = HMASuggestionsHub(2026)

    assert hub.timeout is None
    assert button_labels(hub) == ["Suggest Category Changes"]
