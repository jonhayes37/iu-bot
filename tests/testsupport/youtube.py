"""Stand-ins for the YouTube Data API client."""

import json
from unittest import mock

from googleapiclient.errors import HttpError


def make_http_error(reason: str | None = "backendError", status: int = 403) -> HttpError:
    """An `HttpError` like the one the Google client raises, carrying the API's error `reason`."""
    response = mock.Mock(status=status, reason="error")
    errors = [{"reason": reason, "message": reason}] if reason else []
    body = {"error": {"code": status, "message": reason or "error", "errors": errors}}
    return HttpError(response, json.dumps(body).encode())


def make_youtube_client() -> mock.MagicMock:
    """
    A fake YouTube API client. Calls chain like the real one, so set results with e.g.
    `client.playlistItems.return_value.insert.return_value.execute.return_value = {...}`, or make a
    call fail with `.execute.side_effect = make_http_error("quotaExceeded")`. Every call is recorded
    on the mocks (`client.playlists.return_value.insert.assert_called_once_with(...)`).
    """
    client = mock.MagicMock(name="youtube")
    # Reading a playlist ends after one page unless a test sets up more
    client.playlistItems.return_value.list_next.return_value = None
    return client
