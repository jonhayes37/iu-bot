"""Tests for triggers/releases.py: YouTube links posted in #new-releases."""

import logging
from datetime import datetime, timezone
from unittest import mock

import pytest

from config import EMOJI_IU, Database
from db.releases import add_new_release, get_playlist_id_for_year, mark_release_processed, save_new_playlist
from triggers.releases import _process_release_url, get_eligible_year, store_new_release, store_new_releases

VIDEO_A, VIDEO_B = "aaaaaaaaaa1", "bbbbbbbbbb2"
POSTED = datetime(2026, 3, 17, 15, 0, tzinfo=timezone.utc)


def _url(video_id):
    return f"https://youtu.be/{video_id}"


def _snippet(published="2026-03-10T12:00:00Z"):
    return {"title": "A video", "publishedAt": published}


@pytest.fixture(autouse=True)
def _releases_database(databases):
    databases(Database.RELEASES)


@pytest.fixture(name="youtube", autouse=True)
def _youtube(monkeypatch):
    """The YouTube calls: every video exists (published this year), playlists can be made, adds succeed."""
    calls = mock.Mock()
    calls.snippets.side_effect = lambda ids: {video_id: _snippet() for video_id in ids}
    calls.create.return_value = "PL2026"
    calls.add.return_value = True
    monkeypatch.setattr("triggers.releases.get_video_snippets", calls.snippets)
    monkeypatch.setattr("triggers.releases.create_releases_playlist", calls.create)
    monkeypatch.setattr("triggers.releases.add_video_to_playlist", calls.add)
    return calls


@pytest.fixture(name="post")
def _post(make_message):
    def build(text, created_at=POSTED):
        message = make_message(text)
        message.created_at = created_at
        return message

    return build


def _rows(query):
    return [(r["video_id"], r["processed"]) for r in query(Database.RELEASES, "SELECT * FROM new_releases")]


class TestEligibleYear:
    """December belongs to the next year's awards."""

    @pytest.mark.parametrize("month, year", [(1, 2026), (6, 2026), (11, 2026), (12, 2027)])
    def test_by_month(self, month, year):
        assert get_eligible_year(datetime(2026, month, 15, tzinfo=timezone.utc)) == year


class TestStoringALink:
    """A new link is stored, put on the year's playlist, and marked with a reaction."""

    async def test_a_new_release_is_stored_added_to_the_playlist_and_marked_processed(self, post, query, youtube):
        message = post(f"new mv {_url(VIDEO_A)}")

        await store_new_release(message)

        assert _rows(query) == [(VIDEO_A, 1)]
        youtube.add.assert_called_once_with("PL2026", VIDEO_A)
        message.add_reaction.assert_awaited_once_with(EMOJI_IU)

    async def test_the_years_playlist_is_created_once_and_remembered(self, post, youtube):
        await store_new_release(post(_url(VIDEO_A)))
        await store_new_release(post(_url(VIDEO_B)))

        youtube.create.assert_called_once_with(2026)
        assert get_playlist_id_for_year(2026) == "PL2026"
        assert [c.args[0] for c in youtube.add.call_args_list] == ["PL2026", "PL2026"]

    async def test_an_existing_playlist_is_reused(self, post, youtube):
        save_new_playlist(2026, "PLexisting")

        await store_new_release(post(_url(VIDEO_A)))

        youtube.create.assert_not_called()
        youtube.add.assert_called_once_with("PLexisting", VIDEO_A)

    async def test_the_message_time_is_what_is_stored(self, post, query):
        await store_new_release(post(_url(VIDEO_A)))

        assert query(Database.RELEASES, "SELECT timestamp FROM new_releases")[0]["timestamp"] == POSTED.isoformat()

    async def test_a_message_with_no_link_does_nothing(self, post, youtube):
        message = post("just chatting")

        await store_new_release(message)

        youtube.snippets.assert_not_called()
        message.add_reaction.assert_not_awaited()

    async def test_a_link_that_is_not_a_youtube_video_does_nothing(self, post, youtube):
        await store_new_release(post("https://example.com/watch?v=abc"))

        youtube.snippets.assert_not_called()

    async def test_several_links_in_one_message_are_all_stored_with_one_reaction(self, post, query):
        message = post(f"{_url(VIDEO_A)} and {_url(VIDEO_B)}")

        await store_new_release(message)

        assert sorted(_rows(query)) == [(VIDEO_A, 1), (VIDEO_B, 1)]
        message.add_reaction.assert_awaited_once()


class TestDuplicatesAndRetries:
    """The same link twice, and links that didn't make it onto the playlist."""

    async def test_a_link_already_on_the_playlist_gets_no_second_reaction(self, post, youtube):
        first = post(_url(VIDEO_A))
        await store_new_release(first)
        second = post(_url(VIDEO_A))

        await store_new_release(second)

        second.add_reaction.assert_not_awaited()
        assert youtube.add.call_count == 1

    async def test_a_link_recorded_earlier_but_never_added_is_retried(self, post, query, youtube):
        add_new_release(VIDEO_A, _url(VIDEO_A), "old-message", POSTED)      # e.g. YouTube's quota ran out that day
        message = post(_url(VIDEO_A))

        await store_new_release(message)

        youtube.add.assert_called_once()
        assert _rows(query) == [(VIDEO_A, 1)]
        message.add_reaction.assert_awaited_once()

    async def test_a_playlist_that_cannot_be_created_leaves_the_link_pending_without_a_reaction(
            self, post, query, youtube):
        youtube.create.return_value = None
        message = post(_url(VIDEO_A))

        await store_new_release(message)

        assert _rows(query) == [(VIDEO_A, 0)]
        message.add_reaction.assert_not_awaited()
        assert get_playlist_id_for_year(2026) is None

    async def test_a_video_youtube_refuses_stays_pending_without_a_reaction(self, post, query, youtube):
        youtube.add.return_value = False
        message = post(_url(VIDEO_A))

        await store_new_release(message)

        assert _rows(query) == [(VIDEO_A, 0)]
        message.add_reaction.assert_not_awaited()


class TestWhichVideosCount:
    """Only music from the current awards year is collected."""

    async def test_a_video_published_in_an_earlier_year_is_skipped(self, post, query, youtube, caplog):
        youtube.snippets.side_effect = lambda ids: {v: _snippet("2025-06-01T00:00:00Z") for v in ids}
        message = post(_url(VIDEO_A))

        with caplog.at_level(logging.INFO, logger="iu-bot"):
            await store_new_release(message)

        assert _rows(query) == []
        message.add_reaction.assert_not_awaited()
        assert "Video year (2025) does not match active year (2026)" in caplog.text

    async def test_a_december_video_posted_in_december_counts_for_the_next_year(self, post, youtube, query):
        youtube.snippets.side_effect = lambda ids: {v: _snippet("2026-12-05T00:00:00Z") for v in ids}
        message = post(_url(VIDEO_A), created_at=datetime(2026, 12, 6, tzinfo=timezone.utc))

        await store_new_release(message)

        youtube.create.assert_called_once_with(2027)
        assert _rows(query) == [(VIDEO_A, 1)]

    async def test_a_november_video_shared_in_december_belongs_to_a_different_year_and_is_skipped(
            self, post, youtube, query):
        youtube.snippets.side_effect = lambda ids: {v: _snippet("2026-11-20T00:00:00Z") for v in ids}
        message = post(_url(VIDEO_A), created_at=datetime(2026, 12, 6, tzinfo=timezone.utc))

        await store_new_release(message)

        assert _rows(query) == []

    async def test_a_video_youtube_cannot_find_is_skipped_with_a_warning(self, post, youtube, query, caplog):
        youtube.snippets.side_effect = lambda ids: {}
        message = post(_url(VIDEO_A))

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await store_new_release(message)

        assert "Could not fetch publish date for aaaaaaaaaa1" in caplog.text
        assert _rows(query) == []

    async def test_without_a_youtube_client_nothing_is_stored(self, post, youtube, query, caplog):
        youtube.snippets.side_effect = lambda ids: None

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await store_new_release(post(_url(VIDEO_A)))

        assert "No YouTube client available; skipping 1 release links." in caplog.text
        assert _rows(query) == []


class TestBatches:
    """A backfill hands over many messages at once."""

    async def test_all_the_videos_are_looked_up_in_one_request(self, post, youtube):
        messages = [post(_url(VIDEO_A)), post("no link"), post(f"{_url(VIDEO_B)} {_url(VIDEO_A)}")]

        await store_new_releases(messages)

        youtube.snippets.assert_called_once_with([VIDEO_A, VIDEO_B, VIDEO_A])

    async def test_only_messages_that_added_something_get_the_reaction(self, post):
        first, second, third = post(_url(VIDEO_A)), post(_url(VIDEO_A)), post("nothing")

        await store_new_releases([first, second, third])

        first.add_reaction.assert_awaited_once()
        second.add_reaction.assert_not_awaited()          # the same video was already added by the first
        third.add_reaction.assert_not_awaited()

    async def test_no_messages_do_nothing(self, youtube):
        await store_new_releases([])

        youtube.snippets.assert_not_called()


class TestProcessReleaseUrl:
    """The worker that runs in a thread."""

    def test_an_error_is_logged_and_reported_as_not_processed(self, monkeypatch, caplog):
        monkeypatch.setattr("triggers.releases.add_new_release", mock.Mock(side_effect=RuntimeError("disk full")))

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            result = _process_release_url(_url(VIDEO_A), VIDEO_A, "1", POSTED, 2026, POSTED)

        assert result is False
        assert "Failed to process release aaaaaaaaaa1: disk full" in caplog.text

    def test_a_processed_link_is_not_processed_again(self):
        assert _process_release_url(_url(VIDEO_A), VIDEO_A, "1", POSTED, 2026, POSTED) is True
        mark_release_processed(VIDEO_A)

        assert _process_release_url(_url(VIDEO_A), VIDEO_A, "2", POSTED, 2026, POSTED) is False
