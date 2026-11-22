"""Fixtures for the stats/ tests."""

import textwrap

import pytest


@pytest.fixture(name="list_file")
def make_list_file(tmp_path):
    """Writes text (dedented) to a file in tmp_path and returns its path."""
    def write(text: str, name: str = "event_2026_stats.txt"):
        path = tmp_path / name
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
        return path
    return write
