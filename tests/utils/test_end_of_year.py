"""Tests for utils/end_of_year.py

The awards year runs December 1 to November 30 on purpose (the videos are made in December), and the
switchover happens at midnight Toronto time. Toronto is UTC-5 in winter, so 05:00 UTC is midnight.
"""

import pytest

from utils.end_of_year import get_current_award_year


@pytest.mark.parametrize("utc_moment, expected_year", [
    ("2026-01-01 12:00:00", 2026),
    ("2026-06-15 12:00:00", 2026),
    ("2026-11-30 12:00:00", 2026),
    # Last second of November 30 in Toronto is still the 2026 awards
    ("2026-12-01 04:59:59", 2026),
    # From midnight on December 1 in Toronto it is the next year's awards
    ("2026-12-01 05:00:00", 2027),
    ("2026-12-15 12:00:00", 2027),
    ("2026-12-31 23:59:59", 2027),
    # After New Year the calendar year has caught up
    ("2027-01-01 05:00:00", 2027),
])
def test_award_year_follows_the_december_offset(frozen_time, utc_moment, expected_year):
    frozen_time(utc_moment)

    assert get_current_award_year() == expected_year


def test_uses_toronto_time_not_utc(frozen_time):
    # 03:00 UTC on December 1 is still the evening of November 30 in Toronto
    frozen_time("2026-12-01 03:00:00")

    assert get_current_award_year() == 2026
