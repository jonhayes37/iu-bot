"""Tests for db/releases.py"""

import sqlite3
from datetime import datetime, timezone

import pytest

from config import Database
from db.releases import (
    AddResult, add_new_release, get_playlist_id_for_year, mark_release_processed, save_new_playlist
)

POSTED = datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _releases_database(databases):
    databases(Database.RELEASES)


class TestAddNewRelease:
    """add_new_release says whether a link is new, still waiting for the playlist, or already handled."""

    def test_a_new_video_is_added_and_starts_unprocessed(self, query):
        result = add_new_release("vid1", "https://youtu.be/vid1", "m1", POSTED)

        assert result is AddResult.ADDED
        row = query(Database.RELEASES, "SELECT * FROM new_releases")[0]
        assert (row["video_id"], row["original_url"], row["message_id"], row["processed"]) == \
            ("vid1", "https://youtu.be/vid1", "m1", 0)

    def test_the_message_time_is_stored_not_the_time_of_saving(self, query):
        add_new_release("vid1", "u", "m1", POSTED)

        assert query(Database.RELEASES, "SELECT timestamp FROM new_releases")[0]["timestamp"] == POSTED.isoformat()

    def test_a_video_that_never_reached_the_playlist_is_pending(self):
        add_new_release("vid1", "u", "m1", POSTED)

        assert add_new_release("vid1", "u", "m2", POSTED) is AddResult.PENDING

    def test_a_video_already_on_the_playlist_is_a_duplicate(self):
        add_new_release("vid1", "u", "m1", POSTED)
        mark_release_processed("vid1")

        assert add_new_release("vid1", "u", "m2", POSTED) is AddResult.DUPLICATE

    def test_a_repeat_does_not_add_a_second_row(self, query):
        add_new_release("vid1", "u", "m1", POSTED)
        add_new_release("vid1", "u", "m2", POSTED)

        assert len(query(Database.RELEASES, "SELECT * FROM new_releases")) == 1

    def test_one_message_can_hold_several_videos(self, query):
        assert add_new_release("vid1", "u1", "m1", POSTED) is AddResult.ADDED
        assert add_new_release("vid2", "u2", "m1", POSTED) is AddResult.ADDED

        assert len(query(Database.RELEASES, "SELECT * FROM new_releases WHERE message_id = 'm1'")) == 2


class TestMarkReleaseProcessed:
    """mark_release_processed flags a video as on the playlist."""

    def test_marks_only_that_video(self, query):
        add_new_release("vid1", "u1", "m1", POSTED)
        add_new_release("vid2", "u2", "m2", POSTED)

        mark_release_processed("vid1")

        rows = {row["video_id"]: row["processed"] for row in query(Database.RELEASES, "SELECT * FROM new_releases")}
        assert rows == {"vid1": 1, "vid2": 0}

    def test_an_unknown_video_is_ignored(self, query):
        mark_release_processed("nope")

        assert query(Database.RELEASES, "SELECT * FROM new_releases") == []


class TestPlaylists:
    """There is one playlist per year."""

    def test_no_playlist_yet(self):
        assert get_playlist_id_for_year(2026) is None

    def test_a_saved_playlist_is_found_by_year(self):
        save_new_playlist(2026, "PL2026")
        save_new_playlist(2027, "PL2027")

        assert get_playlist_id_for_year(2026) == "PL2026"
        assert get_playlist_id_for_year(2027) == "PL2027"
        assert get_playlist_id_for_year(2025) is None

    def test_the_same_playlist_id_cannot_be_saved_twice(self):
        save_new_playlist(2026, "PL2026")

        with pytest.raises(sqlite3.IntegrityError):
            save_new_playlist(2027, "PL2026")
