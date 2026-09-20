"""Tests for utils/timestamps.py"""

from datetime import datetime, timezone

import pytest

from utils.timestamps import parse_db_timestamp


def test_parses_a_sqlite_timestamp_as_utc():
    parsed = parse_db_timestamp("2026-03-17 15:00:00")

    assert parsed == datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc)
    assert parsed.tzinfo is timezone.utc


def test_result_can_be_compared_with_an_aware_datetime():
    # A naive result would raise TypeError here
    assert parse_db_timestamp("2026-01-01 00:00:00") < datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("bad_value", [
    "",
    "2026-03-17",                 # no time
    "2026-03-17T15:00:00",        # ISO 'T' separator, not what SQLite CURRENT_TIMESTAMP writes
    "2026-03-17 15:00:00.123",    # fractional seconds
    "2026-13-01 00:00:00",        # month out of range
    "not a date",
])
def test_rejects_anything_that_is_not_a_current_timestamp_value(bad_value):
    with pytest.raises(ValueError):
        parse_db_timestamp(bad_value)
