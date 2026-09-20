"""Tests for db/lists.py: list events and members' submissions."""

import sqlite3

import pytest

from config import Database
from db.lists import (
    SaveOutcome, close_event, create_new_event, get_all_submissions, get_event_details, get_user_submission,
    save_submission, set_event_message_id
)


@pytest.fixture(autouse=True)
def _databases(databases):
    databases(Database.LISTS, Database.MERCH)


def _event(event_id="mid_2026", name="Mid-year List", count=10, placeholder="1. Song"):
    return create_new_event(event_id, name, count, placeholder)


class TestEvents:
    """Creating, reading and closing list events."""

    def test_create_and_read_back(self):
        assert _event() is True

        details = get_event_details("mid_2026")
        assert (details["event_name"], details["expected_count"], details["placeholder_text"]) == \
            ("Mid-year List", 10, "1. Song")
        assert details["is_active"] == 1
        assert details["message_id"] is None

    def test_an_event_id_can_only_be_used_once(self):
        _event(name="first")

        assert _event(name="second") is False
        assert get_event_details("mid_2026")["event_name"] == "first"

    def test_unknown_event_is_none(self):
        assert get_event_details("nope") is None

    def test_closing_marks_it_inactive(self):
        _event()

        assert close_event("mid_2026") is True

        assert get_event_details("mid_2026")["is_active"] == 0

    def test_closing_an_unknown_event_is_false(self):
        assert close_event("nope") is False

    def test_closing_twice_still_reports_the_event_exists(self):
        _event()
        close_event("mid_2026")

        assert close_event("mid_2026") is True

    def test_linking_the_announcement_message(self):
        _event()

        assert set_event_message_id("mid_2026", "999") is True

        assert get_event_details("mid_2026")["message_id"] == "999"

    def test_linking_a_message_to_an_unknown_event_is_false(self):
        assert set_event_message_id("nope", "999") is False


class TestSaveSubmission:
    """One submission per member per event, which they can replace."""

    @pytest.fixture(autouse=True)
    def _an_event(self):
        _event()

    def test_a_new_submission_is_saved_in_full(self):
        assert save_submission("mid_2026", 1, "jo", "raw", "1. clean", "u1,u2") is SaveOutcome.SAVED

        [row] = get_all_submissions("mid_2026")
        assert (row["user_id"], row["username"], row["raw_text"], row["cleaned_text"], row["extracted_urls"]) == \
            (1, "jo", "raw", "1. clean", "u1,u2")

    def test_submitting_again_replaces_the_earlier_one(self):
        save_submission("mid_2026", 1, "jo", "first", "c1", "")

        save_submission("mid_2026", 1, "jo", "second", "c2", "")

        rows = get_all_submissions("mid_2026")
        assert [row["raw_text"] for row in rows] == ["second"]

    def test_members_do_not_overwrite_each_other(self):
        save_submission("mid_2026", 1, "jo", "a", "a", "")
        save_submission("mid_2026", 2, "sam", "b", "b", "")

        assert sorted(row["username"] for row in get_all_submissions("mid_2026")) == ["jo", "sam"]

    def test_a_submission_for_an_unknown_event_is_rejected(self):
        # Foreign keys are enforced
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            save_submission("nope", 1, "jo", "raw", "c", "")

    def test_the_users_previous_text_can_be_fetched_for_the_form(self):
        assert get_user_submission("mid_2026", 1) is None

        save_submission("mid_2026", 1, "jo", "my raw list", "c", "")

        assert get_user_submission("mid_2026", 1) == "my raw list"
        assert get_user_submission("mid_2026", 2) is None

    def test_export_only_includes_the_requested_event(self):
        _event("other", "Other", 5, "")
        save_submission("mid_2026", 1, "jo", "a", "a", "")
        save_submission("other", 2, "sam", "b", "b", "")

        assert [row["username"] for row in get_all_submissions("mid_2026")] == ["jo"]

    def test_no_submissions_is_an_empty_list(self):
        assert get_all_submissions("mid_2026") == []

    def test_deleting_an_event_deletes_its_submissions(self, execute, query):
        save_submission("mid_2026", 1, "jo", "a", "a", "")

        execute(Database.LISTS, "DELETE FROM list_events WHERE event_id = 'mid_2026'")

        assert query(Database.LISTS, "SELECT * FROM list_submissions") == []


class TestSaveSubmissionWithAPerk:
    """A bonus pick uses up a Merch Booth item in the same transaction as the list."""

    @pytest.fixture(autouse=True)
    def _event_and_perk(self, execute):
        _event()
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (1, 'WAYLT', 2)")

    def test_saves_the_list_and_uses_one_item(self, query):
        outcome = save_submission("mid_2026", 1, "jo", "raw", "c", "", use_item="WAYLT")

        assert outcome is SaveOutcome.SAVED
        assert len(get_all_submissions("mid_2026")) == 1
        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 1

    def test_the_item_code_is_case_insensitive(self, query):
        save_submission("mid_2026", 1, "jo", "raw", "c", "", use_item="waylt")

        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 1

    def test_without_the_item_nothing_is_saved(self):
        outcome = save_submission("mid_2026", 2, "sam", "raw", "c", "", use_item="WAYLT")

        assert outcome is SaveOutcome.ITEM_MISSING
        assert get_all_submissions("mid_2026") == []

    def test_a_failed_save_does_not_cost_the_user_their_item(self, query):
        # The event doesn't exist, so the list can't be saved after the item was used
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            save_submission("nope", 1, "jo", "raw", "c", "", use_item="WAYLT")

        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 2

    def test_the_last_item_is_removed_from_inventory(self, query):
        save_submission("mid_2026", 1, "jo", "a", "a", "", use_item="WAYLT")
        save_submission("mid_2026", 1, "jo", "b", "b", "", use_item="WAYLT")

        assert query(Database.MERCH, "SELECT * FROM user_inventory") == []

    def test_no_perk_leaves_the_merch_database_alone(self, query):
        save_submission("mid_2026", 1, "jo", "raw", "c", "")

        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 2
