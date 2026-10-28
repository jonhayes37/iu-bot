"""Tests for db/top_songs.py

Every function works on the awards year it is given (the year of the hub that asked).
"""

import pytest

from config import Database
from db.top_songs import get_all_top_songs, get_user_top_songs, save_top_songs


@pytest.fixture(autouse=True)
def _top_songs_database(databases):
    databases(Database.TOP_SONGS)


def _save(user_id=1, username="jo", t25="raw25", hms="rawhm", year=2026):
    save_top_songs(year, user_id, username, t25, f"clean {t25}", "u1,u2", hms, f"clean {hms}", "u3")


def test_saved_submission_is_stored_in_full_for_the_year(query):
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


def test_the_same_user_can_submit_in_different_years(query):
    _save(t25="this year")

    _save(t25="next year", year=2027)

    assert len(query(Database.TOP_SONGS, "SELECT * FROM eoy_top_songs")) == 2


class TestGetUserTopSongs:
    """Pre-fills the form with what the user sent last time."""

    def test_none_when_they_have_not_submitted(self):
        assert get_user_top_songs(2026, 1) is None

    def test_returns_only_the_raw_text(self):
        _save(t25="my list", hms="my mentions")

        assert get_user_top_songs(2026, 1) == {"top_25_raw": "my list", "hms_raw": "my mentions"}

    def test_another_years_submission_is_not_returned(self):
        _save(year=2025)

        assert get_user_top_songs(2026, 1) is None

    def test_other_users_are_not_returned(self):
        _save(user_id=2)

        assert get_user_top_songs(2026, 1) is None


class TestGetAllTopSongs:
    """The export for one awards year."""

    def test_empty(self):
        assert get_all_top_songs(2026) == []

    def test_returns_every_submission_for_the_year_as_dicts(self):
        _save(user_id=1, username="a")
        _save(user_id=2, username="b")

        rows = get_all_top_songs(2026)

        assert sorted(row["username"] for row in rows) == ["a", "b"]
        assert rows[0]["top_25_clean"].startswith("clean")

    def test_other_years_are_left_out(self):
        _save(user_id=1, year=2025)
        _save(user_id=2)

        assert [row["user_id"] for row in get_all_top_songs(2026)] == [2]
