"""Tests for services/listen_game_playlist.py"""

import asyncio
import logging
from unittest import mock

import pytest

from db.listen_game import Round, RoundStatus
from services.listen_game_playlist import (
    SUBMISSION_LOCK, PlaylistOutcome, get_host_name, put_song_in_round_playlist
)
from services.youtube import QuotaExceededError


@pytest.fixture(name="youtube")
def _youtube_calls(monkeypatch):
    """The YouTube calls the service makes, replaced by mocks that succeed by default."""
    calls = mock.Mock()
    calls.remove.return_value = True
    calls.create.return_value = "NEWPL"
    calls.add.return_value = True
    monkeypatch.setattr("services.listen_game_playlist.remove_video_from_playlist", calls.remove)
    monkeypatch.setattr("services.listen_game_playlist.create_listen_game_playlist", calls.create)
    monkeypatch.setattr("services.listen_game_playlist.add_video_to_playlist", calls.add)
    monkeypatch.setattr("services.listen_game_playlist.update_round_playlist_db", calls.save)
    return calls


def _round(playlist_id=None):
    return Round(round_id=7, game_id=1, host_id=101, status=RoundStatus.SUBMITTING, playlist_id=playlist_id)


class TestPutSongInRoundPlaylist:
    """A submission goes into the round's playlist, which is created on the first song."""

    def test_adds_to_an_existing_playlist(self, youtube):
        outcome = put_song_in_round_playlist("Jo", _round("PLold"), "vid1")

        assert outcome == (PlaylistOutcome.ADDED, "PLold")
        youtube.add.assert_called_once_with("PLold", "vid1")
        youtube.create.assert_not_called()
        youtube.remove.assert_not_called()

    def test_creates_the_playlist_for_the_first_song_and_saves_it(self, youtube):
        active_round = _round(None)

        outcome = put_song_in_round_playlist("Jo", active_round, "vid1")

        assert outcome == (PlaylistOutcome.ADDED, "NEWPL")
        youtube.create.assert_called_once_with("Jo")
        youtube.save.assert_called_once_with(7, "NEWPL")
        assert active_round.playlist_id == "NEWPL"
        youtube.add.assert_called_once_with("NEWPL", "vid1")

    def test_a_replaced_song_is_removed_first(self, youtube):
        order = mock.Mock()
        order.attach_mock(youtube.remove, "remove")
        order.attach_mock(youtube.add, "add")

        put_song_in_round_playlist("Jo", _round("PLold"), "new", previous_video_id="old")

        assert [c[0] for c in order.mock_calls] == ["remove", "add"]
        youtube.remove.assert_called_once_with("PLold", "old")

    def test_a_replaced_song_needs_a_playlist_to_be_removed_from(self, youtube):
        put_song_in_round_playlist("Jo", _round(None), "new", previous_video_id="old")

        youtube.remove.assert_not_called()

    def test_failing_to_remove_the_old_song_does_not_stop_the_new_one(self, youtube, caplog):
        youtube.remove.return_value = False

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            outcome = put_song_in_round_playlist("Jo", _round("PLold"), "new", previous_video_id="old")

        assert outcome == (PlaylistOutcome.ADDED, "PLold")
        assert "Failed to remove old video old" in caplog.text

    def test_a_playlist_that_cannot_be_created_is_reported(self, youtube):
        youtube.create.return_value = None
        active_round = _round(None)

        outcome = put_song_in_round_playlist("Jo", active_round, "vid1")

        assert outcome == (PlaylistOutcome.CREATE_FAILED, None)
        youtube.add.assert_not_called()
        youtube.save.assert_not_called()
        assert active_round.playlist_id is None

    def test_a_song_that_cannot_be_added_is_reported_with_the_playlist(self, youtube):
        youtube.add.return_value = False

        assert put_song_in_round_playlist("Jo", _round("PLold"), "vid1") == (PlaylistOutcome.ADD_FAILED, "PLold")

    def test_quota_running_out_while_adding(self, youtube):
        youtube.add.side_effect = QuotaExceededError(RuntimeError("limit"))

        assert put_song_in_round_playlist("Jo", _round("PLold"), "vid1") == (PlaylistOutcome.QUOTA_EXCEEDED, "PLold")

    def test_quota_running_out_while_creating_keeps_no_playlist(self, youtube):
        youtube.create.side_effect = QuotaExceededError(RuntimeError("limit"))

        assert put_song_in_round_playlist("Jo", _round(None), "vid1") == (PlaylistOutcome.QUOTA_EXCEEDED, None)

    def test_quota_after_creating_still_returns_the_new_playlist(self, youtube):
        # The playlist exists and was saved, so the retry must reuse it rather than create a second one
        youtube.add.side_effect = QuotaExceededError(RuntimeError("limit"))
        active_round = _round(None)

        outcome = put_song_in_round_playlist("Jo", active_round, "vid1")

        assert outcome == (PlaylistOutcome.QUOTA_EXCEEDED, "NEWPL")
        assert active_round.playlist_id == "NEWPL"

    def test_quota_running_out_while_removing(self, youtube):
        youtube.remove.side_effect = QuotaExceededError(RuntimeError("limit"))

        outcome = put_song_in_round_playlist("Jo", _round("PLold"), "new", previous_video_id="old")

        assert outcome == (PlaylistOutcome.QUOTA_EXCEEDED, "PLold")
        youtube.add.assert_not_called()


class TestGetHostName:
    """The playlist is named after the listener."""

    def test_uses_the_members_display_name(self, make_guild, make_member):
        guild = make_guild()
        guild.members = [make_member(user_id=101, name="Jo")]

        assert get_host_name(guild, 101) == "Jo"

    def test_a_member_who_left_is_unknown(self, make_guild):
        assert get_host_name(make_guild(), 101) == "Unknown"


def test_submissions_are_processed_one_at_a_time():
    assert isinstance(SUBMISSION_LOCK, asyncio.Lock)
