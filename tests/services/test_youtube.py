"""Tests for services/youtube.py

The real YouTube API is never used: the `youtube_client` fixture stands in for it.
"""

import logging
import threading
from datetime import datetime, timezone
from unittest import mock

import pytest

from services.youtube import get_yt_service as real_get_yt_service
from services.youtube import (
    VIDEOS_PER_REQUEST, QuotaExceededError, _YouTubeServiceCache, add_video_to_playlist, contains_youtube_url,
    create_listen_game_playlist, create_playlist, create_releases_playlist, extract_video_id, get_playlist_video_ids,
    get_video_snippets, get_video_title, parse_publish_date, remove_video_from_playlist
)

VIDEO = "dQw4w9WgXcQ"


class TestExtractVideoId:
    """Finding the 11 character video ID in the ways people paste YouTube links."""

    @pytest.mark.parametrize("url", [
        f"https://www.youtube.com/watch?v={VIDEO}",
        f"https://youtube.com/watch?v={VIDEO}",
        f"http://www.youtube.com/watch?v={VIDEO}",
        f"https://m.youtube.com/watch?v={VIDEO}",
        f"https://music.youtube.com/watch?v={VIDEO}",
        f"youtube.com/watch?v={VIDEO}",
        f"https://youtu.be/{VIDEO}",
        f"https://youtu.be/{VIDEO}?t=42",
        f"https://www.youtube.com/embed/{VIDEO}",
        f"https://www.youtube.com/v/{VIDEO}",
        f"https://www.youtube.com/watch?feature=share&v={VIDEO}&list=PLabc",
        f"<https://youtu.be/{VIDEO}>",
        f"Check this out https://youtu.be/{VIDEO} it is great",
    ])
    def test_recognised_links(self, url):
        assert extract_video_id(url) == VIDEO

    def test_ids_can_contain_dashes_and_underscores(self):
        assert extract_video_id("https://youtu.be/a-b_c-d_e-f") == "a-b_c-d_e-f"

    def test_the_first_link_in_a_message_wins(self):
        assert extract_video_id("https://youtu.be/aaaaaaaaaaa and https://youtu.be/bbbbbbbbbbb") == "aaaaaaaaaaa"

    @pytest.mark.parametrize("text", [
        "",
        "no link here",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/tooshort",
        "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx",
        "https://www.youtube.com/",
    ])
    def test_things_that_are_not_a_video_link(self, text):
        assert extract_video_id(text) is None

    def test_contains_youtube_url_agrees(self):
        assert contains_youtube_url(f"listen: https://youtu.be/{VIDEO}") is True
        assert contains_youtube_url("no link") is False
        assert contains_youtube_url("") is False


def test_quota_error_says_why():
    error = QuotaExceededError(ValueError("daily limit"))

    assert str(error) == "Quota exceeded: daily limit"


class TestParsePublishDate:
    """YouTube sends ISO 8601 dates ending in Z."""

    def test_reads_a_utc_timestamp(self):
        parsed = parse_publish_date({"publishedAt": "2026-03-17T15:00:00Z"})

        assert parsed == datetime(2026, 3, 17, 15, 0, 0, tzinfo=timezone.utc)
        assert parsed.tzinfo is not None

    def test_a_missing_date_is_an_error(self):
        with pytest.raises(KeyError):
            parse_publish_date({})


def test_the_shared_client_comes_from_the_cache(monkeypatch):
    # The name is imported at the top: the suite replaces services.youtube.get_yt_service to block real API use
    monkeypatch.setattr("services.youtube._yt_service_cache.get", lambda: "the client")

    assert real_get_yt_service() == "the client"


class TestServiceCache:
    """One client per thread, built lazily from token.json."""

    @pytest.fixture
    def token(self, tmp_path, monkeypatch):
        path = tmp_path / "token.json"
        path.write_text("{}")
        monkeypatch.setenv("TOKEN_DIR", str(path))
        return path

    @pytest.fixture
    def google(self, monkeypatch):
        """Replaces the Google libraries so no real credentials or network are involved."""
        credentials = mock.Mock()
        credentials.from_authorized_user_file.return_value = "creds"
        build = mock.Mock(side_effect=lambda *_, **__: mock.MagicMock(name="client"))
        monkeypatch.setattr("services.youtube.Credentials", credentials)
        monkeypatch.setattr("services.youtube.build", build)
        return credentials, build

    def test_without_a_token_path_there_is_no_client(self, caplog):
        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            assert _YouTubeServiceCache().get() is None

        assert "token.json missing" in caplog.text

    def test_a_token_path_that_does_not_exist_is_no_client(self, tmp_path, monkeypatch, google):
        monkeypatch.setenv("TOKEN_DIR", str(tmp_path / "missing.json"))

        assert _YouTubeServiceCache().get() is None
        google[1].assert_not_called()

    def test_builds_a_youtube_v3_client_from_the_token(self, token, google):
        credentials, build = google

        client = _YouTubeServiceCache().get()

        credentials.from_authorized_user_file.assert_called_once_with(
            str(token), ["https://www.googleapis.com/auth/youtube"])
        build.assert_called_once_with("youtube", "v3", credentials="creds")
        assert client is not None

    @pytest.mark.usefixtures("token")
    def test_the_client_is_built_only_once_per_thread(self, google):
        cache = _YouTubeServiceCache()

        first, second = cache.get(), cache.get()

        assert first is second
        assert google[1].call_count == 1

    @pytest.mark.usefixtures("token")
    def test_each_thread_gets_its_own_client(self, google):
        cache = _YouTubeServiceCache()
        clients = []
        main_client = cache.get()

        def fetch():
            clients.append(cache.get())

        thread = threading.Thread(target=fetch)
        thread.start()
        thread.join()

        assert clients[0] is not main_client
        assert google[1].call_count == 2

    @pytest.mark.usefixtures("google")
    def test_a_missing_token_is_retried_next_time(self, tmp_path, monkeypatch):
        cache = _YouTubeServiceCache()
        path = tmp_path / "token.json"
        monkeypatch.setenv("TOKEN_DIR", str(path))
        assert cache.get() is None

        path.write_text("{}")

        assert cache.get() is not None


class TestCreatePlaylist:
    """Playlists are created unlisted."""

    def test_no_client_means_no_playlist(self, monkeypatch):
        monkeypatch.setattr("services.youtube.get_yt_service", lambda: None)

        assert create_playlist("Title") is None

    def test_returns_the_new_playlist_id_and_sends_the_right_request(self, youtube_client):
        youtube_client.playlists.return_value.insert.return_value.execute.return_value = {"id": "PL123"}

        assert create_playlist("My Playlist", "About it") == "PL123"

        youtube_client.playlists.return_value.insert.assert_called_once_with(
            part="snippet,status",
            body={"snippet": {"title": "My Playlist", "description": "About it"},
                  "status": {"privacyStatus": "unlisted"}})

    def test_quota_exhaustion_is_raised_so_callers_can_wait(self, youtube_client, http_error):
        youtube_client.playlists.return_value.insert.return_value.execute.side_effect = http_error("quotaExceeded")

        with pytest.raises(QuotaExceededError):
            create_playlist("Title")

    def test_other_api_errors_return_none(self, youtube_client, http_error, caplog):
        youtube_client.playlists.return_value.insert.return_value.execute.side_effect = http_error("backendError")

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            assert create_playlist("Title") is None

        assert "Failed to create custom YouTube playlist" in caplog.text

    def test_an_error_with_no_details_is_not_mistaken_for_quota(self, youtube_client, http_error):
        youtube_client.playlists.return_value.insert.return_value.execute.side_effect = http_error(None)

        assert create_playlist("Title") is None

    def test_releases_playlist_is_named_for_the_year(self, youtube_client):
        youtube_client.playlists.return_value.insert.return_value.execute.return_value = {"id": "PL1"}

        assert create_releases_playlist(2026) == "PL1"

        body = youtube_client.playlists.return_value.insert.call_args.kwargs["body"]
        assert body["snippet"]["title"] == "2026 K-Pop Releases"
        assert body["snippet"]["description"] == "Automated playlist for 2026 K-Pop releases."

    def test_listen_game_playlist_is_named_for_the_host(self, youtube_client):
        youtube_client.playlists.return_value.insert.return_value.execute.return_value = {"id": "PL2"}

        assert create_listen_game_playlist("Jo") == "PL2"

        body = youtube_client.playlists.return_value.insert.call_args.kwargs["body"]
        assert body["snippet"]["title"] == "Listen Game Round - Jo"


class TestGetVideoSnippets:
    """Details for many videos, fetched in batches to save quota."""

    def _respond(self, youtube_client, known):
        """Makes videos.list answer with the snippets of whichever known ids were asked for."""
        def list_videos(part, **kwargs):
            assert part == "snippet"
            asked = kwargs["id"].split(",")
            request = mock.Mock()
            request.execute.return_value = {"items": [{"id": v, "snippet": known[v]} for v in asked if v in known]}
            return request

        youtube_client.videos.return_value.list.side_effect = list_videos

    def test_no_client_is_none(self, monkeypatch):
        monkeypatch.setattr("services.youtube.get_yt_service", lambda: None)

        assert get_video_snippets(["a"]) is None

    def test_returns_snippets_keyed_by_video_id(self, youtube_client):
        self._respond(youtube_client, {"a": {"title": "A"}, "b": {"title": "B"}})

        assert get_video_snippets(["a", "b"]) == {"a": {"title": "A"}, "b": {"title": "B"}}

    def test_private_or_deleted_videos_are_simply_missing(self, youtube_client):
        self._respond(youtube_client, {"a": {"title": "A"}})

        assert get_video_snippets(["a", "gone"]) == {"a": {"title": "A"}}

    def test_no_videos_makes_no_request(self, youtube_client):
        assert get_video_snippets([]) == {}

        youtube_client.videos.return_value.list.assert_not_called()

    def test_repeated_ids_are_asked_for_once_in_order(self, youtube_client):
        self._respond(youtube_client, {"a": {}, "b": {}})

        get_video_snippets(["b", "a", "b", "a"])

        youtube_client.videos.return_value.list.assert_called_once_with(part="snippet", id="b,a")

    def test_requests_are_batched_at_fifty_ids(self, youtube_client):
        ids = [f"v{i:03}" for i in range(120)]
        self._respond(youtube_client, {v: {"title": v} for v in ids})

        result = get_video_snippets(ids)

        calls = youtube_client.videos.return_value.list.call_args_list
        assert [len(c.kwargs["id"].split(",")) for c in calls] == [50, 50, 20]
        assert VIDEOS_PER_REQUEST == 50
        assert len(result) == 120

    def test_a_failed_batch_is_skipped_and_the_rest_still_arrive(self, youtube_client, caplog):
        ids = [f"v{i:03}" for i in range(60)]
        good = mock.Mock()
        good.execute.return_value = {"items": [{"id": "v050", "snippet": {"title": "kept"}}]}
        bad = mock.Mock()
        bad.execute.side_effect = RuntimeError("network down")
        youtube_client.videos.return_value.list.side_effect = [bad, good]

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            result = get_video_snippets(ids)

        assert result == {"v050": {"title": "kept"}}
        assert "error fetching details for 50 videos" in caplog.text

    def test_get_video_title(self, youtube_client):
        self._respond(youtube_client, {"a": {"title": "IU - Good Day"}})

        assert get_video_title("a") == "IU - Good Day"
        assert get_video_title("missing") is None

    def test_get_video_title_without_a_client_is_none(self, monkeypatch):
        monkeypatch.setattr("services.youtube.get_yt_service", lambda: None)

        assert get_video_title("a") is None


class TestRemoveVideoFromPlaylist:
    """Removing looks up the item first, since YouTube deletes by playlist item id."""

    def test_no_client_is_false(self, monkeypatch):
        monkeypatch.setattr("services.youtube.get_yt_service", lambda: None)

        assert remove_video_from_playlist("PL", "vid") is False

    def test_finds_the_item_and_deletes_it(self, youtube_client):
        items = youtube_client.playlistItems.return_value
        items.list.return_value.execute.return_value = {"items": [{"id": "ITEM1"}]}

        assert remove_video_from_playlist("PL", "vid") is True

        items.list.assert_called_once_with(part="id", playlistId="PL", videoId="vid")
        items.delete.assert_called_once_with(id="ITEM1")
        items.delete.return_value.execute.assert_called_once()

    def test_a_video_that_is_not_there_counts_as_removed(self, youtube_client):
        items = youtube_client.playlistItems.return_value
        items.list.return_value.execute.return_value = {"items": []}

        assert remove_video_from_playlist("PL", "vid") is True

        items.delete.assert_not_called()

    def test_an_api_error_is_false(self, youtube_client, http_error, caplog):
        youtube_client.playlistItems.return_value.list.return_value.execute.side_effect = http_error()

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            assert remove_video_from_playlist("PL", "vid") is False

        assert "Failed to remove video vid" in caplog.text

    def test_a_failure_while_deleting_is_false(self, youtube_client, http_error):
        items = youtube_client.playlistItems.return_value
        items.list.return_value.execute.return_value = {"items": [{"id": "ITEM1"}]}
        items.delete.return_value.execute.side_effect = http_error()

        assert remove_video_from_playlist("PL", "vid") is False


class TestGetPlaylistVideoIds:
    """Reading a whole playlist, across pages."""

    @staticmethod
    def _page(*video_ids):
        return {"items": [{"snippet": {"resourceId": {"videoId": v}}} for v in video_ids]}

    def test_no_client_is_none(self, monkeypatch):
        monkeypatch.setattr("services.youtube.get_yt_service", lambda: None)

        assert get_playlist_video_ids("PL") is None

    def test_returns_the_video_ids(self, youtube_client):
        items = youtube_client.playlistItems.return_value
        items.list.return_value.execute.return_value = self._page("a", "b")

        assert get_playlist_video_ids("PL") == {"a", "b"}

        items.list.assert_called_once_with(part="snippet", playlistId="PL", maxResults=50)

    def test_an_empty_playlist_is_an_empty_set_not_none(self, youtube_client):
        youtube_client.playlistItems.return_value.list.return_value.execute.return_value = {"items": []}

        assert get_playlist_video_ids("PL") == set()

    def test_follows_every_page(self, youtube_client):
        items = youtube_client.playlistItems.return_value
        first, second, third = mock.Mock(), mock.Mock(), mock.Mock()
        first.execute.return_value = self._page("a", "b")
        second.execute.return_value = self._page("c")
        third.execute.return_value = self._page("d")
        items.list.return_value = first
        items.list_next.side_effect = [second, third, None]

        assert get_playlist_video_ids("PL") == {"a", "b", "c", "d"}

    def test_quota_exhaustion_is_raised(self, youtube_client, http_error):
        youtube_client.playlistItems.return_value.list.return_value.execute.side_effect = http_error("quotaExceeded")

        with pytest.raises(QuotaExceededError):
            get_playlist_video_ids("PL")

    def test_other_errors_are_none_never_an_empty_set(self, youtube_client, http_error):
        # An unreadable playlist must not look like an empty one, or every song would be added again
        youtube_client.playlistItems.return_value.list.return_value.execute.side_effect = http_error("notFound", 404)

        assert get_playlist_video_ids("PL") is None


class TestAddVideoToPlaylist:
    """Adding a song, and telling the caller why it didn't work."""

    def test_no_client_is_false(self, monkeypatch):
        monkeypatch.setattr("services.youtube.get_yt_service", lambda: None)

        assert add_video_to_playlist("PL", "vid") is False

    def test_sends_the_video_to_the_playlist(self, youtube_client):
        assert add_video_to_playlist("PL", "vid") is True

        youtube_client.playlistItems.return_value.insert.assert_called_once_with(
            part="snippet",
            body={"snippet": {"playlistId": "PL", "resourceId": {"kind": "youtube#video", "videoId": "vid"}}})
        youtube_client.playlistItems.return_value.insert.return_value.execute.assert_called_once()

    def test_quota_exhaustion_is_raised(self, youtube_client, http_error):
        youtube_client.playlistItems.return_value.insert.return_value.execute.side_effect = http_error("quotaExceeded")

        with pytest.raises(QuotaExceededError):
            add_video_to_playlist("PL", "vid")

    def test_a_private_or_deleted_video_is_false_with_a_warning(self, youtube_client, http_error, caplog):
        youtube_client.playlistItems.return_value.insert.return_value.execute.side_effect = \
            http_error("videoNotFound", 404)

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            assert add_video_to_playlist("PL", "vid") is False

        assert "may be private or deleted" in caplog.text

    def test_any_other_error_is_false_and_logged_as_an_error(self, youtube_client, http_error, caplog):
        youtube_client.playlistItems.return_value.insert.return_value.execute.side_effect = http_error("backendError")

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            assert add_video_to_playlist("PL", "vid") is False

        assert "Failed to add video vid" in caplog.text
