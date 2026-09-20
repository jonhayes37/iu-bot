"""Tests for ui/lists.py: the list submission form and its button."""

import logging
from unittest import mock

import discord
import pytest

from config import DEFAULT_ADMIN_USER_ID, Database
from db.lists import close_event, create_new_event, get_all_submissions, get_user_submission, save_submission
from ui.base import DATABASE_ERROR
from ui.lists import DynamicListModal, SubmitListButton, handle_list_button_click
from testsupport.ui import fill, match_custom_id

THREE_SONGS = "IU - Good Day\nBTS - Dynamite\nIVE - Eleven"


@pytest.fixture(autouse=True)
def _databases(databases):
    databases(Database.LISTS, Database.MERCH)


@pytest.fixture(name="admin")
def _admin(interaction, make_member):
    """The admin, reachable through the bot's client, who is told about each submission."""
    person = make_member(user_id=DEFAULT_ADMIN_USER_ID, name="Admin")
    interaction.client.get_user.return_value = person
    return person


def _modal(event_id="mid_2026", name="Mid-year List", count=3, default=None):
    return DynamicListModal(event_id, name, count, "1. Artist // Song", default_text=default)


async def _submit(interaction, modal, text):
    fill(modal.submission_text, text)
    await modal.on_submit(interaction)


class TestListModalSetup:
    """The form adapts to the event."""

    async def test_uses_the_event_name_as_the_title_shortened_to_discords_limit(self):
        modal = _modal(name="A very long event name that goes on and on and on well past the limit")

        assert modal.title == "A very long event name that goes on and on and on well past the limit"[:45]

    async def test_shows_the_placeholder_and_previous_text(self):
        modal = _modal(default="1. old // list")

        assert modal.submission_text.placeholder == "1. Artist // Song"
        assert modal.submission_text.default == "1. old // list"
        assert modal.submission_text.required is True


class TestListModalSubmit:
    """Submitting a list validates it, saves it and tells the admin."""

    @pytest.fixture(autouse=True)
    def _event(self):
        create_new_event("mid_2026", "Mid-year List", 3, "1. Artist // Song")

    async def test_a_valid_list_is_saved_cleaned_and_confirmed(self, interaction, admin):
        await _submit(interaction, _modal(), THREE_SONGS)

        [row] = get_all_submissions("mid_2026")
        assert row["user_id"] == interaction.user.id
        assert row["cleaned_text"] == "1. IU // Good Day\n2. BTS // Dynamite\n3. IVE // Eleven"
        assert row["raw_text"] == THREE_SONGS
        assert interaction.sent[0].content.startswith("Your list has been submitted!")
        assert interaction.sent[0].ephemeral
        assert admin.sent

    async def test_links_are_saved_alongside(self, interaction, admin):
        await _submit(interaction, _modal(), "IU - A (https://youtu.be/aaaaaaaaaaa)\nB - b\nC - c")

        assert get_all_submissions("mid_2026")[0]["extracted_urls"] == "https://youtu.be/aaaaaaaaaaa,,"
        assert admin.sent

    async def test_the_wrong_number_of_songs_is_refused_and_the_list_handed_back(self, interaction):
        await _submit(interaction, _modal(), "IU - Good Day\nBTS - Dynamite")

        [reply] = interaction.sent
        assert reply.content.startswith("❌ **Submission Failed** ❌\nYour main list requires exactly 3 songs")
        assert "but you provided 2." in reply.content
        assert reply.kwargs["file"].filename == "your_list.txt"
        assert reply.kwargs["file"].fp.read() == b"IU - Good Day\nBTS - Dynamite"
        assert get_all_submissions("mid_2026") == []

    async def test_the_admin_is_told_about_a_first_submission(self, interaction, admin):
        await _submit(interaction, _modal(), THREE_SONGS)

        [dm] = admin.sent
        assert dm.content == f"📥 **{interaction.user.display_name}** submitted their list for **Mid-year List**!"

    async def test_the_admin_is_told_about_an_edit(self, interaction, admin):
        await _submit(interaction, _modal(default=THREE_SONGS), "A - a\nB - b\nC - c")

        name = interaction.user.display_name
        assert admin.sent[0].content == f"📥 **{name}** updated their list for **Mid-year List**!"

    async def test_an_admin_not_in_the_cache_is_fetched(self, interaction, admin):
        interaction.client.get_user.return_value = None
        interaction.client.fetch_user.return_value = admin

        await _submit(interaction, _modal(), THREE_SONGS)

        assert admin.sent

    async def test_an_admin_with_closed_dms_does_not_break_the_submission(self, interaction, admin, caplog):
        admin.send.side_effect = discord.Forbidden(mock.Mock(status=403, reason="Forbidden"), "closed")

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await _submit(interaction, _modal(), THREE_SONGS)

        assert len(get_all_submissions("mid_2026")) == 1
        assert "Could not DM admin" in caplog.text

    async def test_a_failed_admin_dm_does_not_break_the_submission(self, interaction, admin, caplog):
        admin.send.side_effect = discord.HTTPException(mock.Mock(status=500, reason="err"), "boom")

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await _submit(interaction, _modal(), THREE_SONGS)

        assert len(get_all_submissions("mid_2026")) == 1
        assert "Failed to send admin notification DM" in caplog.text

    async def test_a_database_failure_reports_the_error_and_hands_the_text_back(self, interaction, execute):
        execute(Database.LISTS, "DROP TABLE list_submissions")
        modal = _modal()
        fill(modal.submission_text, THREE_SONGS)

        try:
            await modal.on_submit(interaction)
        except Exception as error:  # discord.py passes errors from on_submit to on_error
            await modal.on_error(interaction, error)

        [reply] = interaction.sent
        assert reply.content.startswith(DATABASE_ERROR)
        assert reply.kwargs["files"][0].filename == "your_list.txt"
        assert reply.kwargs["files"][0].fp.read() == THREE_SONGS.encode()


class TestWhatAreYouListeningToBonusPick:
    """A 'What Are You Listening To' event allows one extra song to members who own the WAYLT item."""

    @pytest.fixture(autouse=True)
    def _waylt_event(self):
        create_new_event("waylt_1", "What Are You Listening To #1", 3, "1. Artist // Song")

    @staticmethod
    def _modal(default=None):
        return DynamicListModal("waylt_1", "What Are You Listening To #1", 3, "1. Artist // Song", default)

    FOUR_SONGS = THREE_SONGS + "\nEXO - Growl"

    async def test_an_extra_song_uses_up_the_item_and_says_so(self, interaction, admin, execute, query):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (?, 'WAYLT', 1)", interaction.user.id)

        await _submit(interaction, self._modal(), self.FOUR_SONGS)

        assert query(Database.MERCH, "SELECT * FROM user_inventory") == []
        assert get_user_submission("waylt_1", interaction.user.id) == self.FOUR_SONGS
        assert interaction.sent[0].content.startswith("🎟️ **What Are You Listening To Bonus Pick Consumed!**")
        assert admin.sent

    async def test_an_extra_song_without_the_item_is_refused_and_the_list_handed_back(self, interaction):
        await _submit(interaction, self._modal(), self.FOUR_SONGS)

        [reply] = interaction.sent
        assert reply.content.startswith("❌ **Missing Item** ❌\nYou submitted 4 items, but this event only allows 3.")
        assert "`WAYLT`" in reply.content
        assert reply.kwargs["file"].fp.read() == self.FOUR_SONGS.encode()
        assert get_all_submissions("waylt_1") == []

    async def test_editing_a_list_that_already_had_the_extra_song_costs_nothing_more(self, interaction, admin,
                                                                                    execute, query):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (?, 'WAYLT', 2)", interaction.user.id)

        await _submit(interaction, self._modal(default=self.FOUR_SONGS), self.FOUR_SONGS.replace("Growl", "Love Shot"))

        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 2
        assert "Love Shot" in get_user_submission("waylt_1", interaction.user.id)
        assert not interaction.sent[0].content.startswith("🎟️")
        assert admin.sent

    async def test_the_normal_number_of_songs_costs_nothing(self, interaction, admin, execute, query):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (?, 'WAYLT', 1)", interaction.user.id)

        await _submit(interaction, self._modal(), THREE_SONGS)

        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 1
        assert admin.sent

    async def test_two_extra_songs_are_too_many_even_with_the_item(self, interaction, execute):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (?, 'WAYLT', 1)", interaction.user.id)

        await _submit(interaction, self._modal(), self.FOUR_SONGS + "\nA - b")

        assert interaction.sent[0].content.startswith("❌ **Submission Failed** ❌")
        assert get_all_submissions("waylt_1") == []

    async def test_other_events_never_offer_the_extra_song(self, interaction, execute):
        create_new_event("mid_2026", "Mid-year List", 3, "")
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (?, 'WAYLT', 1)", interaction.user.id)
        modal = DynamicListModal("mid_2026", "Mid-year List", 3, "", None)

        await _submit(interaction, modal, self.FOUR_SONGS)

        assert interaction.sent[0].content.startswith("❌ **Submission Failed** ❌")

    async def test_an_event_with_no_fixed_size_never_offers_it(self, interaction):
        create_new_event("free", "What Are You Listening To free-for-all", 0, "")
        modal = DynamicListModal("free", "What Are You Listening To free-for-all", 0, "", None)

        await _submit(interaction, modal, "A - a")

        assert interaction.sent[0].content.startswith("❌ **Submission Failed** ❌")

    async def test_an_item_that_disappears_before_saving_saves_nothing(self, interaction, monkeypatch):
        # e.g. spent in another window between the check and the save
        monkeypatch.setattr("ui.lists.check_user_owns_item", lambda *_: True)

        await _submit(interaction, self._modal(), self.FOUR_SONGS)

        [reply] = interaction.sent
        assert "no longer in your inventory, so nothing was saved" in reply.content
        assert reply.kwargs["file"].fp.read() == self.FOUR_SONGS.encode()
        assert get_all_submissions("waylt_1") == []


class TestSubmitListButton:
    """The button on a list announcement; the event is part of its ID."""

    async def test_an_open_events_button(self):
        button = SubmitListButton("mid_2026")

        assert button.item.custom_id == "submit_list:mid_2026"
        assert (button.item.label, button.item.disabled) == ("Submit Your List", False)

    async def test_a_closed_events_button_is_locked(self):
        button = SubmitListButton("mid_2026", closed=True)

        assert button.item.custom_id == "submit_list:mid_2026_closed"
        assert (button.item.label, button.item.disabled) == ("Submissions Closed", True)

    @pytest.mark.parametrize("custom_id, event_id, closed", [
        ("submit_list:mid_2026", "mid_2026", False),
        ("submit_list:mid_2026_closed", "mid_2026", True),
        ("submit_list:waylt-3", "waylt-3", False),
    ])
    async def test_the_button_is_rebuilt_from_its_id_after_a_restart(self, interaction, custom_id, event_id, closed):
        match = match_custom_id(SubmitListButton, custom_id)

        rebuilt = await SubmitListButton.from_custom_id(interaction, mock.Mock(), match)

        assert (rebuilt.event_id, rebuilt.closed) == (event_id, closed)

    @pytest.mark.parametrize("custom_id", ["submit_list:", "other_button:mid_2026", "submit_list:a:b"])
    async def test_other_ids_are_not_ours(self, custom_id):
        assert match_custom_id(SubmitListButton, custom_id) is None

    async def test_pressing_a_closed_button_says_so(self, interaction):
        await SubmitListButton("mid_2026", closed=True).callback(interaction)

        assert interaction.sent[0].content == "Submissions for this event are closed!"
        assert interaction.sent[0].ephemeral

    async def test_pressing_an_open_button_opens_the_form(self, interaction):
        create_new_event("mid_2026", "Mid-year List", 3, "1. A // B")

        await SubmitListButton("mid_2026").callback(interaction)

        interaction.response.send_modal.assert_awaited_once()

    async def test_an_error_while_pressing_is_reported_to_the_user(self, interaction, execute):
        execute(Database.LISTS, "DROP TABLE list_events")

        await SubmitListButton("mid_2026").callback(interaction)

        assert interaction.sent[0].content == DATABASE_ERROR


class TestHandleListButtonClick:
    """Pressing the button opens the form for an event that is still open."""

    async def test_an_event_that_no_longer_exists(self, interaction):
        await handle_list_button_click(interaction, "gone")

        assert interaction.sent[0].content == "This event no longer exists in the database."
        interaction.response.send_modal.assert_not_awaited()

    async def test_a_closed_event(self, interaction):
        create_new_event("mid_2026", "Mid-year List", 3, "")
        close_event("mid_2026")

        await handle_list_button_click(interaction, "mid_2026")

        assert interaction.sent[0].content == "Submissions for this event are officially closed!"
        interaction.response.send_modal.assert_not_awaited()

    async def test_an_open_event_shows_a_form_set_up_for_it(self, interaction):
        create_new_event("mid_2026", "Mid-year List", 7, "1. Artist // Song")

        await handle_list_button_click(interaction, "mid_2026")

        modal = interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, DynamicListModal)
        assert (modal.event_id, modal.event_name, modal.expected_count) == ("mid_2026", "Mid-year List", 7)
        assert modal.submission_text.placeholder == "1. Artist // Song"
        assert modal.submission_text.default is None

    async def test_the_form_is_prefilled_with_their_earlier_list(self, interaction):
        create_new_event("mid_2026", "Mid-year List", 3, "")
        save_submission("mid_2026", interaction.user.id, "jo", "my old list", "c", "")

        await handle_list_button_click(interaction, "mid_2026")

        assert interaction.response.send_modal.await_args.args[0].submission_text.default == "my old list"
