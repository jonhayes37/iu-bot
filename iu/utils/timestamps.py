"""Helpers for the timestamps stored in the databases."""

from datetime import datetime, timezone


def parse_db_timestamp(value: str) -> datetime:
    """
    Turns a SQLite CURRENT_TIMESTAMP value ("2026-03-17 15:00:00", always UTC) into a timezone-aware
    datetime.
    """
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
