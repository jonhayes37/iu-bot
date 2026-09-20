"""Tests for tasks/common.py"""

import asyncio
import logging

import pytest

from tasks.common import keep_running


class TestKeepRunning:
    """A background loop must survive an error in one tick."""

    async def test_passes_arguments_and_the_result_through(self):
        @keep_running
        async def tick(client, guild_id, *, extra=0):
            return (client, guild_id, extra)

        assert await tick("bot", 5, extra=2) == ("bot", 5, 2)

    async def test_an_error_is_logged_with_a_traceback_and_not_raised(self, caplog):
        @keep_running
        async def flaky_tick():
            raise ValueError("bad row")

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            result = await flaky_tick()

        assert result is None
        record = caplog.records[-1]
        assert "Unhandled error in flaky_tick" in record.getMessage()
        assert isinstance(record.exc_info[1], ValueError)

    async def test_the_next_call_still_runs(self):
        calls = []

        @keep_running
        async def tick():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("first tick fails")
            return "ok"

        assert await tick() is None
        assert await tick() == "ok"

    async def test_keeps_the_name_of_the_task(self):
        @keep_running
        async def check_things():
            return None

        assert check_things.__name__ == "check_things"

    async def test_cancellation_is_not_swallowed(self):
        # Stopping the bot cancels its tasks; that must still work
        @keep_running
        async def tick():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await tick()
