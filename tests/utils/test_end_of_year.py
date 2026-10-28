"""Tests for utils/end_of_year.py

The awards year runs December 1 to November 30 on purpose (the videos are made in December), and the
switchover happens at midnight Toronto time. Toronto is UTC-5 in winter, so 05:00 UTC is midnight.
"""

from datetime import datetime, timezone

import pytest

from utils.end_of_year import award_year_for, get_festivities_year


@pytest.mark.parametrize("utc_moment, expected_year", [
    (datetime(2026, 1, 1, 12, tzinfo=timezone.utc), 2026),
    (datetime(2026, 6, 15, 12, tzinfo=timezone.utc), 2026),
    (datetime(2026, 11, 30, 12, tzinfo=timezone.utc), 2026),
    (datetime(2026, 12, 1, 4, 59, 59, tzinfo=timezone.utc), 2026),     # 23:59:59 on November 30 in Toronto
    (datetime(2026, 12, 1, 5, tzinfo=timezone.utc), 2027),             # midnight on December 1 in Toronto
    (datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc), 2027),
    (datetime(2027, 1, 1, 4, 59, tzinfo=timezone.utc), 2027),          # still December 31 in Toronto
])
def test_a_moment_belongs_to_the_awards_year_with_the_december_offset(utc_moment, expected_year):
    assert award_year_for(utc_moment) == expected_year


@pytest.mark.parametrize("utc_moment, expected_year", [
    ("2026-01-15 12:00:00", 2026),
    ("2026-11-20 12:00:00", 2026),
    # The December festivities (nomination deadline, voting, watch parties) are for the year that just ended
    ("2026-12-01 05:00:00", 2026),
    ("2026-12-11 12:00:00", 2026),
    ("2026-12-31 12:00:00", 2026),
    # New Year in Toronto starts the next one
    ("2027-01-01 05:00:00", 2027),
])
def test_the_festivities_stay_on_the_year_being_celebrated_through_december(frozen_time, utc_moment, expected_year):
    frozen_time(utc_moment)

    assert get_festivities_year() == expected_year


def test_the_festivities_year_uses_toronto_time_not_utc(frozen_time):
    # 03:00 UTC on January 1 is still the evening of December 31 in Toronto
    frozen_time("2027-01-01 03:00:00")

    assert get_festivities_year() == 2026
