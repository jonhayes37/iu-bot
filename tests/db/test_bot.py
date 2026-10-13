"""Tests for db/bot.py"""

from datetime import datetime, timedelta, timezone

import pytest

from config import Database
from db.bot import get_active_bot_status_db, mark_event_notified_db, save_bot_status_db, was_event_notified_db


@pytest.fixture(autouse=True)
def _bot_database(databases):
    databases(Database.BOT)


def _save_at(execute, text, days, created_at):
    execute(Database.BOT, "INSERT INTO statuses (status_text, max_duration_days, created_at) VALUES (?, ?, ?)",
            text, days, created_at)


def test_no_status_saved_means_none():
    assert get_active_bot_status_db() is None


def test_saved_status_is_active(query):
    save_bot_status_db("Listening to IU", 7)

    assert get_active_bot_status_db() == "Listening to IU"
    row = query(Database.BOT, "SELECT status_text, max_duration_days FROM statuses")[0]
    assert (row["status_text"], row["max_duration_days"]) == ("Listening to IU", 7)


def test_latest_status_wins(execute, frozen_time):
    frozen_time("2026-03-03 00:00:00")
    _save_at(execute, "old", 30, "2026-03-01 00:00:00")
    _save_at(execute, "new", 30, "2026-03-02 00:00:00")

    assert get_active_bot_status_db() == "new"


def test_status_expires_after_its_duration(execute, frozen_time):
    _save_at(execute, "short", 2, "2026-03-01 12:00:00")

    frozen_time("2026-03-03 11:59:59")
    assert get_active_bot_status_db() == "short"

    frozen_time("2026-03-03 12:00:01")
    assert get_active_bot_status_db() is None


def test_expiry_is_inclusive_at_the_exact_moment(execute, frozen_time):
    _save_at(execute, "edge", 1, "2026-03-01 12:00:00")
    frozen_time("2026-03-02 12:00:00")

    assert get_active_bot_status_db() == "edge"


def test_an_expired_latest_status_does_not_fall_back_to_an_older_one(execute, frozen_time):
    _save_at(execute, "long ago but lasting", 365, "2026-01-01 00:00:00")
    _save_at(execute, "recent but expired", 1, "2026-03-01 00:00:00")
    frozen_time("2026-03-10 00:00:00")

    assert get_active_bot_status_db() is None


def test_a_status_lasts_as_long_as_asked(execute, frozen_time):
    created = datetime(2026, 3, 1, tzinfo=timezone.utc)
    _save_at(execute, "week", 7, created.strftime("%Y-%m-%d %H:%M:%S"))

    frozen_time((created + timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S"))
    assert get_active_bot_status_db() == "week"
    frozen_time((created + timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S"))
    assert get_active_bot_status_db() is None


def test_an_event_is_not_notified_until_it_is_marked():
    assert not was_event_notified_db(111)

    mark_event_notified_db(111)

    assert was_event_notified_db(111)
    assert not was_event_notified_db(222)


def test_marking_an_event_twice_keeps_one_row(query):
    mark_event_notified_db(111)
    mark_event_notified_db(111)

    assert len(query(Database.BOT, "SELECT * FROM notified_events")) == 1


def test_of_two_statuses_saved_in_the_same_second_the_later_one_wins(execute, frozen_time):
    frozen_time("2026-03-17 12:30:00")
    _save_at(execute, "first", 7, "2026-03-17 12:00:00")
    _save_at(execute, "second", 7, "2026-03-17 12:00:00")

    assert get_active_bot_status_db() == "second"
