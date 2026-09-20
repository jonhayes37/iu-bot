"""Tests for commands/potpourri.py: building a YouTube playlist from a CSV of members' links."""

import logging
from unittest import mock

import discord
import pytest

from commands.potpourri import create_potpourri_playlist
from services.youtube import QuotaExceededError

VIDEO_A1, VIDEO_A2, VIDEO_A3 = "aaaaaaaaaa1", "aaaaaaaaaa2", "aaaaaaaaaa3"
VIDEO_B1, VIDEO_C1 = "bbbbbbbbbb1", "cccccccccc1"


def _url(video_id):
    return f"https://youtu.be/{video_id}"


def _csv(*rows, header="Discord Name,Favourite Link"):
    return (header + "\n" + "\n".join(f"{name},{link}" for name, link in rows)).encode("utf-8")


def _attachment(content: bytes, filename="responses.csv"):
    attachment = mock.MagicMock(spec=discord.Attachment)
    attachment.filename = filename
    attachment.read = mock.AsyncMock(return_value=content)
    return attachment


@pytest.fixture(name="youtube", autouse=True)
def _youtube(monkeypatch):
    """The two YouTube calls the command makes; they succeed unless a test says otherwise."""
    calls = mock.Mock()
    calls.create.return_value = "PLnew"
    calls.add.return_value = True
    monkeypatch.setattr("commands.potpourri.create_playlist", calls.create)
    monkeypatch.setattr("commands.potpourri.add_video_to_playlist", calls.add)
    return calls


def _added(youtube):
    return [call.args[1] for call in youtube.add.call_args_list]


async def _run(admin_interaction, content, title="Potpourri"):
    await create_potpourri_playlist.callback(admin_interaction, _attachment(content), title)
    return admin_interaction.sent[-1].content


class TestCsvHandling:
    """Reading the upload."""

    async def test_it_defers_first_because_a_big_playlist_takes_a_while(self, admin_interaction):
        await _run(admin_interaction, _csv(("Jo", _url(VIDEO_A1))))

        admin_interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    async def test_only_csv_files_are_accepted(self, admin_interaction, youtube):
        await create_potpourri_playlist.callback(admin_interaction, _attachment(b"x", "notes.txt"), "T")

        assert admin_interaction.sent[0].content == "❌ Please upload a valid `.csv` file."
        youtube.create.assert_not_called()

    @pytest.mark.parametrize("header", ["Discord Name,Link", "name,url", "Your Discord username,Video URL",
                                        "Timestamp,Discord,Song Link"])
    async def test_the_name_and_link_columns_are_found_whatever_they_are_called(self, admin_interaction, youtube,
                                                                                header):
        columns = header.split(",")
        row = ["2026-01-01"] * (len(columns) - 2) + ["Jo", _url(VIDEO_A1)]

        await _run(admin_interaction, (header + "\n" + ",".join(row)).encode())

        assert _added(youtube) == [VIDEO_A1]

    async def test_a_csv_without_those_columns_is_refused(self, admin_interaction, youtube):
        text = await _run(admin_interaction, b"Song,Artist\nA,B\n")

        assert text == "❌ Could not identify the 'Name' or 'Link' columns in the CSV."
        youtube.create.assert_not_called()

    async def test_a_byte_order_mark_from_a_spreadsheet_export_is_ignored(self, admin_interaction, youtube):
        content = "﻿Discord Name,Link\nJo,".encode("utf-8") + _url(VIDEO_A1).encode()

        await _run(admin_interaction, content)

        assert _added(youtube) == [VIDEO_A1]

    async def test_rows_without_a_name_or_a_valid_link_are_skipped(self, admin_interaction, youtube):
        await _run(admin_interaction, _csv(("Jo", _url(VIDEO_A1)), ("", _url(VIDEO_B1)), ("Sam", ""),
                                           ("Kit", "not a link"), ("Lee", "https://example.com/x")))

        assert _added(youtube) == [VIDEO_A1]

    async def test_a_file_with_no_usable_links_is_refused(self, admin_interaction, youtube):
        text = await _run(admin_interaction, _csv(("Jo", "nope"), ("Sam", "still nope")))

        assert text == "❌ No valid YouTube links were found in the uploaded file."
        youtube.create.assert_not_called()

    async def test_names_and_links_are_trimmed(self, admin_interaction, youtube):
        await _run(admin_interaction, _csv(("  Jo  ", f"  {_url(VIDEO_A1)}  ")))

        assert _added(youtube) == [VIDEO_A1]

    async def test_a_file_that_is_not_text_is_reported_not_crashed(self, admin_interaction, caplog):
        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            text = await _run(admin_interaction, b"\xff\xfe\x00\x01\x02")

        assert text.startswith("❌ An error occurred while processing the file:")
        assert "Error processing watch party CSV" in caplog.text


class TestOrdering:
    """Videos are added in round-robin order so no member's picks clump together."""

    async def test_alternates_between_members(self, admin_interaction, youtube):
        await _run(admin_interaction, _csv(
            ("Jo", _url(VIDEO_A1)), ("Jo", _url(VIDEO_A2)), ("Jo", _url(VIDEO_A3)),
            ("Sam", _url(VIDEO_B1)), ("Kit", _url(VIDEO_C1))))

        # Jo, Sam, Kit take turns; when Sam and Kit run out the rest are Jo's
        assert _added(youtube) == [VIDEO_A1, VIDEO_B1, VIDEO_C1, VIDEO_A2, VIDEO_A3]

    async def test_a_video_shared_by_two_members_is_added_once_to_the_first(self, admin_interaction, youtube):
        await _run(admin_interaction, _csv(("Jo", _url(VIDEO_A1)), ("Sam", _url(VIDEO_A1)), ("Sam", _url(VIDEO_B1))))

        assert _added(youtube) == [VIDEO_A1, VIDEO_B1]

    async def test_the_playlist_takes_the_given_title(self, admin_interaction, youtube):
        await _run(admin_interaction, _csv(("Jo", _url(VIDEO_A1))), title="Summer Potpourri")

        youtube.create.assert_called_once_with("Summer Potpourri", "K-Potpourri Playlist")
        assert youtube.add.call_args.args[0] == "PLnew"


class TestOutcome:
    """What the admin is told."""

    async def test_success(self, admin_interaction):
        text = await _run(admin_interaction, _csv(("Jo", _url(VIDEO_A1)), ("Sam", _url(VIDEO_B1))))

        assert text == ("✅ **Watch Party Playlist Created!**\n"
                        "Successfully organized and added **2/2** videos in round-robin order.\n\n"
                        "🔗 https://www.youtube.com/playlist?list=PLnew")

    async def test_a_playlist_that_cannot_be_created(self, admin_interaction, youtube):
        youtube.create.return_value = None

        text = await _run(admin_interaction, _csv(("Jo", _url(VIDEO_A1))))

        assert text == "❌ Failed to create the YouTube playlist. Check your API Quota and bot logs."
        youtube.add.assert_not_called()

    async def test_videos_that_could_not_be_added_are_listed_without_embeds(self, admin_interaction, youtube):
        youtube.add.side_effect = lambda _, video_id: video_id != VIDEO_B1

        text = await _run(admin_interaction, _csv(("Jo", _url(VIDEO_A1)), ("Sam", _url(VIDEO_B1))))

        assert "**1/2** videos" in text
        assert f"❌ **Failed to add:**\n• <{_url(VIDEO_B1)}>" in text          # <> stops Discord embedding it

    async def test_only_the_first_ten_failures_are_listed(self, admin_interaction, youtube):
        youtube.add.return_value = False
        links = [("Jo", _url(f"vvvvvvvvv{i:02}")) for i in range(13)]

        text = await _run(admin_interaction, _csv(*links))

        assert text.count("• <") == 10
        assert "*...and 3 more.*" in text
        assert "**0/13** videos" in text

    async def test_running_out_of_youtube_quota_stops_and_reports_progress(self, admin_interaction, youtube):
        youtube.add.side_effect = [True, QuotaExceededError(RuntimeError("limit"))]

        text = await _run(admin_interaction, _csv(
            ("Jo", _url(VIDEO_A1)), ("Sam", _url(VIDEO_B1)), ("Kit", _url(VIDEO_C1))))

        assert text.startswith("⚠️ **Quota Exceeded mid-process!**\nAdded 1 out of 3 videos")
        assert "🔗 https://www.youtube.com/playlist?list=PLnew" in text
        assert f"• <{_url(VIDEO_B1)}>" in text                   # the one that hit the limit
        assert "*...and 1 more unattempted videos.*" in text     # the one never tried
        assert youtube.add.call_count == 2                        # it stopped trying
