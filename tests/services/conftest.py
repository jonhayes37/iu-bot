"""Fixtures for the services tests."""

import pytest

from testsupport.youtube import make_http_error, make_youtube_client


@pytest.fixture
def youtube_client(monkeypatch):
    """
    A fake YouTube API client, installed as the one `services.youtube` uses. Also returned to the test
    so it can set results and check calls (see `testsupport.youtube.make_youtube_client`).
    """
    client = make_youtube_client()
    monkeypatch.setattr("services.youtube.get_yt_service", lambda: client)
    return client


@pytest.fixture
def http_error():
    """Factory for the errors the Google API client raises: `http_error("quotaExceeded")`."""
    return make_http_error
