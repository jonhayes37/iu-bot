"""Tests for ui/base.py: how errors from buttons, menus and forms are reported."""

import logging
import sqlite3
from unittest import mock

import discord
import pytest
from discord import app_commands

from db.errors import InvalidStateError
from ui.base import (
    DATABASE_ERROR, GENERIC_ERROR, STATE_CHANGED, SafeModal, SafeView, report_interaction_error, reports_errors
)


class TestReportInteractionError:
    """One place tells the user something went wrong, and logs why."""

    async def test_a_database_error_gets_the_database_message_and_a_traceback_in_the_log(self, interaction, caplog):
        error = sqlite3.OperationalError("database is locked")

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await report_interaction_error(interaction, error)

        [reply] = interaction.sent
        assert (reply.content, reply.ephemeral) == (DATABASE_ERROR, True)
        record = caplog.records[-1]
        assert "Database error" in record.getMessage() and record.exc_info[1] is error

    async def test_a_state_change_gets_the_moved_on_message_and_only_a_warning(self, interaction, caplog):
        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await report_interaction_error(interaction, InvalidStateError("round already revealed"))

        assert interaction.sent[0].content == STATE_CHANGED
        assert [r.levelno for r in caplog.records] == [logging.WARNING]

    async def test_any_other_error_gets_the_generic_message(self, interaction, caplog):
        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await report_interaction_error(interaction, ValueError("bug"))

        assert interaction.sent[0].content == GENERIC_ERROR
        assert "Unexpected error" in caplog.text

    async def test_the_real_error_is_found_inside_a_command_invoke_error(self, interaction):
        wrapped = app_commands.CommandInvokeError(mock.Mock(), sqlite3.OperationalError("locked"))

        await report_interaction_error(interaction, wrapped)

        assert interaction.sent[0].content == DATABASE_ERROR

    async def test_a_state_change_inside_a_command_invoke_error(self, interaction):
        wrapped = app_commands.CommandInvokeError(mock.Mock(), InvalidStateError("moved on"))

        await report_interaction_error(interaction, wrapped)

        assert interaction.sent[0].content == STATE_CHANGED

    async def test_replies_privately(self, interaction):
        await report_interaction_error(interaction, ValueError())

        assert interaction.sent[0].ephemeral

    async def test_uses_a_followup_when_the_interaction_was_already_answered(self, interaction):
        await interaction.response.defer()

        await report_interaction_error(interaction, ValueError())

        assert interaction.sent[0].via == "followup"

    async def test_uses_the_response_when_nothing_has_been_sent_yet(self, interaction):
        await report_interaction_error(interaction, ValueError())

        assert interaction.sent[0].via == "response"

    async def test_text_the_user_typed_is_attached_so_it_is_not_lost(self, interaction):
        await report_interaction_error(interaction, sqlite3.Error("x"),
                                       keep_text={"your_list.txt": "1. IU // Good Day"})

        [reply] = interaction.sent
        assert reply.content.endswith("What you typed is attached so you don't lose it.")
        [attachment] = reply.kwargs["files"]
        assert attachment.filename == "your_list.txt"
        assert attachment.fp.read() == b"1. IU // Good Day"

    async def test_several_pieces_of_text_become_several_files(self, interaction):
        await report_interaction_error(interaction, ValueError(), keep_text={"a.txt": "one", "b.txt": "two"})

        assert [f.filename for f in interaction.sent[0].kwargs["files"]] == ["a.txt", "b.txt"]

    async def test_blank_text_is_not_attached_and_the_note_is_left_out(self, interaction):
        await report_interaction_error(interaction, ValueError(), keep_text={"a.txt": "   \n", "b.txt": ""})

        [reply] = interaction.sent
        assert reply.kwargs["files"] == []
        assert reply.content == GENERIC_ERROR

    async def test_a_failure_to_reply_is_logged_not_raised(self, interaction, caplog):
        interaction.response.send_message.side_effect = discord.HTTPException(
            mock.Mock(status=500, reason="Server Error"), "boom")

        with caplog.at_level(logging.WARNING, logger="iu-bot"):
            await report_interaction_error(interaction, ValueError())

        assert "Could not tell the user about an error" in caplog.text


class TestSafeViewAndModal:
    """Views and forms report their own errors."""

    async def test_a_view_reports_errors_from_its_items(self, interaction):
        view = SafeView()

        await view.on_error(interaction, sqlite3.Error("x"), mock.Mock())

        assert interaction.sent[0].content == DATABASE_ERROR

    async def test_a_modal_reports_errors_from_its_submit(self, interaction):
        modal = SafeModal(title="A form")

        await modal.on_error(interaction, ValueError("bug"))

        assert interaction.sent[0].content == GENERIC_ERROR


class TestReportsErrors:
    """Dynamic buttons need the same reporting, because discord.py only logs their errors."""

    class Item:
        """Stands in for a DynamicItem."""

        @reports_errors
        async def works(self, _, value):
            return f"done {value}"

        @reports_errors
        async def fails(self, interaction):
            raise sqlite3.OperationalError("locked")

    async def test_passes_the_result_through(self, interaction):
        assert await self.Item().works(interaction, 5) == "done 5"
        assert interaction.sent == []

    async def test_reports_a_failure_and_returns_none(self, interaction):
        assert await self.Item().fails(interaction) is None

        assert interaction.sent[0].content == DATABASE_ERROR

    async def test_keeps_the_name_of_the_wrapped_callback(self):
        assert self.Item.works.__name__ == "works"

    @pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
    async def test_does_not_swallow_a_request_to_stop(self, interaction, exception):
        class Item:
            """Stands in for a DynamicItem."""

            @reports_errors
            async def stops(self, _):
                raise exception()

        with pytest.raises(exception):
            await Item().stops(interaction)
