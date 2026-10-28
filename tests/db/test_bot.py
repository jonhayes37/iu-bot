"""Tests for db/bot.py"""

from datetime import datetime, timedelta, timezone

import pytest

from config import Database
from db.bot import (
    EndOfYearPost, EndOfYearPostKind, SecretPoll, SecretVoteResult, close_end_of_year, create_secret_poll,
    delete_secret_poll, get_active_bot_status_db, get_due_secret_polls, get_end_of_year_posts,
    get_recent_secret_polls, get_secret_poll, get_secret_poll_counts, get_secret_poll_options,
    is_end_of_year_closed, mark_event_notified_db, mark_secret_poll_closed, record_end_of_year_post,
    record_secret_vote, save_bot_status_db, set_secret_poll_message, was_event_notified_db
)


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


class TestEndOfYearPosts:
    """The end of year hubs are remembered so /end-of-year-close can find them."""

    def test_none_recorded(self):
        assert get_end_of_year_posts(2026) == []

    def test_posts_come_back_for_their_year_in_the_order_posted(self):
        record_end_of_year_post(2026, EndOfYearPostKind.SUGGESTIONS, 10, 100)
        record_end_of_year_post(2026, EndOfYearPostKind.VOTING, 11, 101)
        record_end_of_year_post(2025, EndOfYearPostKind.NOMINATIONS, 10, 50)

        assert get_end_of_year_posts(2026) == [
            EndOfYearPost(EndOfYearPostKind.SUGGESTIONS, 10, 100), EndOfYearPost(EndOfYearPostKind.VOTING, 11, 101)]

    def test_recording_the_same_message_twice_keeps_one(self):
        record_end_of_year_post(2026, EndOfYearPostKind.VOTING, 11, 101)
        record_end_of_year_post(2026, EndOfYearPostKind.VOTING, 11, 101)

        assert len(get_end_of_year_posts(2026)) == 1


class TestEndOfYearClosed:
    """Closing a year's festivities."""

    def test_a_year_starts_open(self):
        assert is_end_of_year_closed(2026) is False

    def test_closing_says_it_changed_something_the_first_time_only(self):
        assert close_end_of_year(2026) is True
        assert close_end_of_year(2026) is False

        assert is_end_of_year_closed(2026) is True

    def test_years_are_closed_separately(self):
        close_end_of_year(2025)

        assert is_end_of_year_closed(2026) is False


NOON = datetime(2026, 12, 12, 12, 0, 0, tzinfo=timezone.utc)
CLOSES = NOON + timedelta(hours=24)


def _poll(options=("A", "B", "C"), closes_at=CLOSES, title="Tiebreaker"):
    return create_secret_poll(title, list(options), 1, 10, closes_at)


class TestSecretPolls:
    """Creating, finding and closing secret polls."""

    def test_a_new_poll_is_saved_open_with_its_options_in_order(self):
        poll_id = _poll()

        assert get_secret_poll(poll_id) == SecretPoll(poll_id, "Tiebreaker", 1, 10, None, CLOSES, False)
        assert get_secret_poll_options(poll_id) == ["A", "B", "C"]

    def test_the_post_is_recorded(self):
        poll_id = _poll()

        set_secret_poll_message(poll_id, 555)

        assert get_secret_poll(poll_id).message_id == 555

    def test_an_unknown_poll_is_none(self):
        assert get_secret_poll(99) is None

    def test_deleting_takes_its_options_and_votes_too(self, query):
        poll_id = _poll()
        record_secret_vote(poll_id, 7, 0, NOON)

        delete_secret_poll(poll_id)

        assert get_secret_poll(poll_id) is None
        assert query(Database.BOT, "SELECT * FROM secret_poll_options") == []
        assert query(Database.BOT, "SELECT * FROM secret_poll_votes") == []

    def test_recent_polls_come_newest_first(self):
        first, second = _poll(title="First"), _poll(title="Second")

        assert [poll.poll_id for poll in get_recent_secret_polls()] == [second, first]
        assert len(get_recent_secret_polls(limit=1)) == 1

    def test_only_open_polls_past_their_time_are_due(self):
        due = _poll(closes_at=NOON)
        _poll(closes_at=NOON + timedelta(seconds=1))
        closed = _poll(closes_at=NOON - timedelta(hours=1))
        mark_secret_poll_closed(closed)

        assert [poll.poll_id for poll in get_due_secret_polls(NOON)] == [due]

    def test_closing_happens_once(self):
        poll_id = _poll()

        assert mark_secret_poll_closed(poll_id) is True
        assert mark_secret_poll_closed(poll_id) is False
        assert get_secret_poll(poll_id).closed is True


class TestSecretVotes:
    """One vote per member, changeable until the poll closes."""

    def test_votes_are_counted_per_option_including_none(self):
        poll_id = _poll()
        for user_id, position in ((1, 0), (2, 0), (3, 2)):
            assert record_secret_vote(poll_id, user_id, position, NOON) is SecretVoteResult.VOTED

        assert get_secret_poll_counts(poll_id) == [("A", 2), ("B", 0), ("C", 1)]

    def test_voting_again_replaces_the_vote(self):
        poll_id = _poll()
        record_secret_vote(poll_id, 1, 0, NOON)

        record_secret_vote(poll_id, 1, 1, NOON)

        assert get_secret_poll_counts(poll_id) == [("A", 0), ("B", 1), ("C", 0)]

    def test_polls_are_counted_separately(self):
        first, second = _poll(), _poll()
        record_secret_vote(first, 1, 0, NOON)

        assert get_secret_poll_counts(second) == [("A", 0), ("B", 0), ("C", 0)]

    def test_no_vote_at_or_after_the_closing_time(self):
        poll_id = _poll()

        assert record_secret_vote(poll_id, 1, 0, CLOSES) is SecretVoteResult.CLOSED
        assert get_secret_poll_counts(poll_id)[0] == ("A", 0)

    def test_no_vote_once_closed_even_before_the_time(self):
        poll_id = _poll()
        mark_secret_poll_closed(poll_id)

        assert record_secret_vote(poll_id, 1, 0, NOON) is SecretVoteResult.CLOSED

    def test_an_unknown_poll_counts_as_closed(self):
        assert record_secret_vote(99, 1, 0, NOON) is SecretVoteResult.CLOSED

    def test_an_option_the_poll_does_not_have_is_refused(self):
        poll_id = _poll(options=("A", "B"))

        assert record_secret_vote(poll_id, 1, 2, NOON) is SecretVoteResult.NO_SUCH_OPTION
        assert get_secret_poll_counts(poll_id) == [("A", 0), ("B", 0)]
