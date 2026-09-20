"""Tests for db/top_songs.py

The awards year runs December 1 to November 30, so a submission made in December belongs to next year.
"""

import pytest

from config import Database
from db.top_songs import get_all_top_songs, get_user_top_songs, save_top_songs


@pytest.fixture(autouse=True)
def _top_songs_database(databases, frozen_time):
    databases(Database.TOP_SONGS)
    frozen_time("2026-10-15 12:00:00")


def _save(user_id=1, username="jo", t25="raw25", hms="rawhm"):
    return save_top_songs(user_id, username, t25, f"clean {t25}", "u1,u2", hms, f"clean {hms}", "u3")


def test_save_returns_the_award_year():
    assert _save() == 2026


def test_a_submission_made_in_december_belongs_to_the_next_year(frozen_time):
    frozen_time("2026-12-05 12:00:00")

    assert _save() == 2027


def test_saved_submission_is_stored_in_full(query):
    _save(user_id=5, username="jo")

    row = query(Database.TOP_SONGS, "SELECT * FROM eoy_top_songs")[0]
    assert (row["user_id"], row["award_year"], row["username"]) == (5, 2026, "jo")
    assert (row["top_25_raw"], row["top_25_clean"], row["top_25_urls"]) == ("raw25", "clean raw25", "u1,u2")
    assert (row["hms_raw"], row["hms_clean"], row["hms_urls"]) == ("rawhm", "clean rawhm", "u3")


def test_saving_again_replaces_the_users_submission(query):
    _save(t25="first")

    _save(t25="second")

    rows = query(Database.TOP_SONGS, "SELECT top_25_raw FROM eoy_top_songs")
    assert [row["top_25_raw"] for row in rows] == ["second"]


def test_the_same_user_can_submit_in_different_years(frozen_time, query):
    _save(t25="this year")
    frozen_time("2027-03-01 12:00:00")

    _save(t25="next year")

    assert len(query(Database.TOP_SONGS, "SELECT * FROM eoy_top_songs")) == 2


class TestGetUserTopSongs:
    """Pre-fills the form with what the user sent last time."""

    def test_none_when_they_have_not_submitted(self):
        assert get_user_top_songs(1) is None

    def test_returns_only_the_raw_text(self):
        _save(t25="my list", hms="my mentions")

        assert get_user_top_songs(1) == {"top_25_raw": "my list", "hms_raw": "my mentions"}

    def test_last_years_submission_is_not_returned(self, frozen_time):
        _save()
        frozen_time("2027-03-01 12:00:00")

        assert get_user_top_songs(1) is None

    def test_other_users_are_not_returned(self):
        _save(user_id=2)

        assert get_user_top_songs(1) is None


class TestGetAllTopSongs:
    """The export for the current awards year."""

    def test_empty(self):
        assert get_all_top_songs() == []

    def test_returns_every_submission_this_year_as_dicts(self):
        _save(user_id=1, username="a")
        _save(user_id=2, username="b")

        rows = get_all_top_songs()

        assert sorted(row["username"] for row in rows) == ["a", "b"]
        assert rows[0]["top_25_clean"].startswith("clean")

    def test_other_years_are_left_out(self, frozen_time):
        _save(user_id=1)
        frozen_time("2027-03-01 12:00:00")
        _save(user_id=2)

        assert [row["user_id"] for row in get_all_top_songs()] == [2]
