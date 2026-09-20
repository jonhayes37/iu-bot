"""Tests for commands/lists.py: list events for admins."""

import logging
from unittest import mock

import discord
import pytest

from commands.lists import _process_export_data, close_list_event, create_list_event, export_lists
from config import Database
from db.lists import close_event, create_new_event, get_event_details, save_submission, set_event_message_id
from ui.lists import SubmitListButton

NOT_FOUND = discord.NotFound(mock.Mock(status=404, reason="Not Found"), "Unknown")


@pytest.fixture(autouse=True)
def _databases(databases):
    databases(Database.LISTS)


@pytest.fixture(name="admin")
def _admin(make_guild, make_interaction):
    """An admin running the command in #general of a server."""
    return make_interaction(guild=make_guild(channels=("general",)), administrator=True)


class TestCreateListEvent:
    """/create-list-event."""

    @pytest.mark.parametrize("event_id", ["", "has space", "semi;colon", "a" * 65, "émoji", "slash/x"])
    async def test_an_event_id_with_unusable_characters_is_refused(self, admin, event_id):
        await create_list_event.callback(admin, event_id, "Name")

        assert admin.sent[0].content.startswith("The event ID can only use letters, numbers, `-` and `_`")
        assert admin.channel.sent == []

    @pytest.mark.parametrize("event_id", ["mid_2026", "waylt-3", "A", "a" * 64])
    async def test_ids_of_letters_numbers_dash_and_underscore_are_accepted(self, admin, event_id):
        await create_list_event.callback(admin, event_id, "Name")

        assert get_event_details(event_id) is not None

    async def test_an_id_already_in_use_is_refused(self, admin):
        create_new_event("mid_2026", "First", 3, "")

        await create_list_event.callback(admin, "mid_2026", "Second")

        assert admin.sent[0].content == "An event with the ID `mid_2026` already exists."
        assert get_event_details("mid_2026")["event_name"] == "First"
        assert admin.channel.sent == []

    async def test_posts_a_button_announcement_and_remembers_where(self, admin):
        await create_list_event.callback(admin, "mid_2026", "Mid-year List", 10, "1. A // b")

        [post] = admin.channel.sent
        assert post.content == "**Mid-year List**\nClick below to submit your list!"
        [button] = post.kwargs["view"].children
        assert isinstance(button, SubmitListButton) and button.event_id == "mid_2026"
        details = get_event_details("mid_2026")
        assert (details["event_name"], details["expected_count"], details["placeholder_text"]) == \
            ("Mid-year List", 10, "1. A // b")
        assert details["message_id"].startswith(f"{admin.channel.id}:")

    async def test_the_admins_own_confirmation_is_removed_so_only_the_post_remains(self, admin):
        await create_list_event.callback(admin, "mid_2026", "Mid-year List")

        admin.response.defer.assert_awaited_once_with(ephemeral=True)
        admin.delete_original_response.assert_awaited_once()

    async def test_the_expected_count_defaults_to_no_fixed_size(self, admin):
        await create_list_event.callback(admin, "mid_2026", "Mid-year List")

        assert get_event_details("mid_2026")["expected_count"] == 0


class TestCloseListEvent:
    """/close-list-event locks the event and its button."""

    @pytest.fixture(name="event")
    def _event(self, admin):
        """An event whose announcement is message 4242 in another channel of the server."""
        create_new_event("mid_2026", "Mid-year List", 3, "")
        other = admin.guild.text_channels[0]
        set_event_message_id("mid_2026", f"{other.id}:4242")
        return other

    async def test_an_unknown_event(self, admin):
        await close_list_event.callback(admin, "nope")

        assert admin.sent[0].content == "Could not find event `nope` in the database."

    async def test_an_event_that_never_had_an_announcement(self, admin):
        create_new_event("mid_2026", "Mid-year List", 3, "")

        await close_list_event.callback(admin, "mid_2026")

        assert admin.sent[0].content == "Event `mid_2026` exists, but it has no message ID to update."
        assert get_event_details("mid_2026")["is_active"] == 1

    async def test_closes_the_event_and_locks_the_button_on_the_announcement(self, admin, event):
        await close_list_event.callback(admin, "mid_2026")

        assert get_event_details("mid_2026")["is_active"] == 0
        event.fetch_message.assert_awaited_once_with(4242)
        assert admin.sent[0].content == "Event `mid_2026` closed!"
        assert admin.sent[0].ephemeral

    async def test_the_announcement_button_becomes_the_closed_one(self, admin, event):
        message = mock.MagicMock(spec=discord.Message, edit=mock.AsyncMock())
        event.fetch_message = mock.AsyncMock(return_value=message)

        await close_list_event.callback(admin, "mid_2026")

        view = message.edit.await_args.kwargs["view"]
        [button] = view.children
        assert (button.closed, button.item.disabled, button.item.label) == (True, True, "Submissions Closed")

    async def test_an_announcement_in_another_channel_is_found_there(self, admin, make_channel):
        create_new_event("mid_2026", "Mid-year List", 3, "")
        elsewhere = make_channel("community")
        message = mock.MagicMock(spec=discord.Message, edit=mock.AsyncMock())
        elsewhere.fetch_message = mock.AsyncMock(return_value=message)
        admin.guild.channels.append(elsewhere)
        set_event_message_id("mid_2026", f"{elsewhere.id}:99")

        await close_list_event.callback(admin, "mid_2026")

        elsewhere.fetch_message.assert_awaited_once_with(99)
        message.edit.assert_awaited_once()

    async def test_an_older_event_with_a_bare_message_id_is_looked_up_in_the_current_channel(self, admin):
        create_new_event("old", "Old event", 3, "")
        set_event_message_id("old", "777")
        message = mock.MagicMock(spec=discord.Message, edit=mock.AsyncMock())
        admin.channel.fetch_message = mock.AsyncMock(return_value=message)

        await close_list_event.callback(admin, "old")

        admin.channel.fetch_message.assert_awaited_once_with(777)
        assert admin.sent[0].content == "Event `old` closed!"

    async def test_a_channel_that_no_longer_exists_still_closes_the_event(self, admin):
        create_new_event("mid_2026", "Mid-year List", 3, "")
        set_event_message_id("mid_2026", "999999:4242")
        admin.guild.get_channel.side_effect = lambda _: None
        admin.guild.fetch_channel = mock.AsyncMock(side_effect=NOT_FOUND)

        await close_list_event.callback(admin, "mid_2026")

        assert get_event_details("mid_2026")["is_active"] == 0
        assert admin.sent[0].content == \
            "Event closed in DB, but the channel the announcement was posted in no longer exists."

    async def test_a_deleted_announcement_still_closes_the_event(self, admin, event):
        event.fetch_message = mock.AsyncMock(side_effect=NOT_FOUND)

        await close_list_event.callback(admin, "mid_2026")

        assert get_event_details("mid_2026")["is_active"] == 0
        assert admin.sent[0].content == "Event closed in DB, but the original message was deleted from the channel."

    async def test_any_other_failure_editing_the_message_is_reported(self, admin, event, caplog):
        event.fetch_message = mock.AsyncMock(side_effect=RuntimeError("boom"))

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await close_list_event.callback(admin, "mid_2026")

        assert admin.sent[0].content == "Event closed, but failed to edit the message."
        assert "Error updating message for closed event mid_2026" in caplog.text

    async def test_a_failure_to_close_in_the_database_is_reported(self, admin, event, monkeypatch):
        monkeypatch.setattr("commands.lists.close_event", lambda _: False)

        await close_list_event.callback(admin, "mid_2026")

        assert admin.sent[0].content == "Failed to close event in the database."
        event.fetch_message.assert_not_awaited()

    @pytest.mark.usefixtures("event")
    async def test_closing_an_already_closed_event_still_locks_the_button(self, admin):
        close_event("mid_2026")

        await close_list_event.callback(admin, "mid_2026")

        assert admin.sent[0].content == "Event `mid_2026` closed!"


class TestExportLists:
    """/export-lists attaches the lists and a sheet of links."""

    async def test_an_unknown_event(self, admin):
        await export_lists.callback(admin, "nope")

        assert admin.sent[0].content == "Could not find event `nope`."

    async def test_an_event_nobody_has_submitted_to(self, admin):
        create_new_event("mid_2026", "Mid-year List", 3, "")

        await export_lists.callback(admin, "mid_2026")

        assert admin.sent[0].content == "No submissions found for `mid_2026` yet!"

    async def test_attaches_the_lists_and_the_link_sheet(self, admin):
        create_new_event("mid_2026", "Mid-year List", 2, "")
        save_submission("mid_2026", 1, "Jo", "raw", "1. A // a\n2. B // b", "https://youtu.be/aaaaaaaaaaa?t=58s,")
        save_submission("mid_2026", 2, "Sam", "raw", "1. C // c\n2. D // d", ",")

        await export_lists.callback(admin, "mid_2026")

        [reply] = admin.sent
        assert reply.content == "Exported **2** submissions for `mid_2026`!"
        files = {f.filename: f.fp.read().decode("utf-8") for f in reply.kwargs["files"]}
        assert files["mid_2026_stats.txt"] == "Jo\n1. A // a\n2. B // b\nSam\n1. C // c\n2. D // d\n"
        assert files["mid_2026_urls.txt"].startswith("URL REFERENCE SHEET: Mid-year List\n" + "=" * 50)
        sheet = files["mid_2026_urls.txt"]
        assert "--- Jo ---\n1. A // a\n-> https://youtu.be/aaaaaaaaaaa?t=58s (starts at 0:58)" in sheet
        assert "Sam" not in sheet


class TestProcessExportData:
    """The link sheet lists each pick that had a link, with the time it starts at."""

    @staticmethod
    def _sheet(clean_text, urls, username="Jo"):
        _, sheet = _process_export_data("Event", [{"username": username, "cleaned_text": clean_text,
                                                   "extracted_urls": urls}])
        return sheet

    @pytest.mark.parametrize("url, suffix", [
        ("https://youtu.be/x?t=58", " (starts at 0:58)"),
        ("https://youtu.be/x?t=58s", " (starts at 0:58)"),
        ("https://youtu.be/x?t=123", " (starts at 2:03)"),
        ("https://youtu.be/x?t=1m2s", " (starts at 1:02)"),
        ("https://youtu.be/x?t=2m", " (starts at 2:00)"),
        ("https://youtu.be/x?t=1h1m1s", " (starts at 1:01:01)"),
        ("https://youtu.be/x?t=1h", " (starts at 1:00:00)"),
        ("https://youtu.be/x?t=3600", " (starts at 1:00:00)"),
        ("https://www.youtube.com/watch?v=x&t=90s", " (starts at 1:30)"),
        ("https://youtu.be/x", ""),
    ])
    def test_the_start_time_is_shown_in_minutes_and_seconds(self, url, suffix):
        assert self._sheet("1. A // a", url).endswith(f"1. A // a\n-> {url}{suffix}\n\n")

    def test_the_stats_file_has_every_members_list(self):
        stats, _ = _process_export_data("Event", [
            {"username": "Jo", "cleaned_text": "1. A // a", "extracted_urls": ""},
            {"username": "Sam", "cleaned_text": "1. B // b", "extracted_urls": ""}])

        assert stats == "Jo\n1. A // a\nSam\n1. B // b\n"

    def test_members_without_links_are_left_off_the_sheet(self):
        sheet = self._sheet("1. A // a\n2. B // b", ",")

        assert sheet == "URL REFERENCE SHEET: Event\n" + "=" * 50 + "\n\n"

    def test_only_picks_that_have_a_link_are_listed_with_their_own_line(self):
        b_url, c_url = "https://youtu.be/bbbbbbbbbbb", "https://youtu.be/ccccccccccc"
        sheet = self._sheet("1. A // a\n2. B // b\n3. C // c", f",{b_url},{c_url}")

        assert f"2. B // b\n-> {b_url}" in sheet and f"3. C // c\n-> {c_url}" in sheet
        assert "1. A" not in sheet

    def test_a_link_with_no_matching_line_is_labelled_by_position(self):
        assert "Pick #2\n-> https://youtu.be/bbbbbbbbbbb" in self._sheet("1. A // a", ",https://youtu.be/bbbbbbbbbbb")
