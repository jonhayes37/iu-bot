"""Tests for commands/releases.py: /backfill-new-releases."""

import logging
from datetime import datetime, timezone
from unittest import mock

import pytest

from commands.releases import BACKFILL_BATCH_SIZE, backfill_releases
from config import Channel


@pytest.fixture(name="store", autouse=True)
def _store(monkeypatch):
    """The function that records a batch of messages' links, which the tests inspect."""
    stored = mock.AsyncMock()
    monkeypatch.setattr("commands.releases.store_new_releases", stored)
    return stored


@pytest.fixture(name="history")
def _history(make_guild, make_interaction, make_message):
    """An admin's interaction in a server whose #new-releases holds `count` messages (call it with the count)."""
    def build(count):
        guild = make_guild(channels=(Channel.NEW_RELEASES,))
        releases = guild.text_channels[0]
        messages = [make_message(f"message {i}") for i in range(count)]
        calls = []

        def history(**kwargs):
            calls.append(kwargs)

            async def generate():
                for message in messages:
                    yield message
            return generate()

        releases.history = history
        interaction = make_interaction(guild=guild, administrator=True)
        return interaction, messages, calls

    return build


async def test_a_server_without_the_releases_channel(make_guild, make_interaction, store):
    interaction = make_interaction(guild=make_guild(channels=("general",)), administrator=True)

    await backfill_releases.callback(interaction, "2025-12-01")

    assert (interaction.sent[0].content, interaction.sent[0].ephemeral) == \
        ("Could not find the #new-releases channel.", True)
    store.assert_not_awaited()


@pytest.mark.parametrize("date", ["", "yesterday", "2025/12/01", "12-01-2025", "2025-13-01", "2025-12-32"])
async def test_a_date_that_is_not_year_month_day_is_refused(history, store, date):
    interaction, _, calls = history(3)

    await backfill_releases.callback(interaction, date)

    assert interaction.sent[0].content == "❌ Invalid date format. Please use YYYY-MM-DD (e.g., 2025-12-01)."
    assert interaction.sent[0].ephemeral
    assert calls == [] and store.await_count == 0


async def test_scans_the_history_from_the_date_oldest_first_in_utc(history):
    interaction, _, calls = history(3)

    await backfill_releases.callback(interaction, "2025-12-01")

    assert calls == [{"limit": None, "oldest_first": True,
                      "after": datetime(2025, 12, 1, tzinfo=timezone.utc)}]


async def test_is_acknowledged_publicly_first_because_it_can_take_a_long_time(history):
    interaction, _, _ = history(3)

    await backfill_releases.callback(interaction, "2025-12-01")

    interaction.response.defer.assert_awaited_once_with(ephemeral=False)


async def test_messages_are_processed_in_batches_of_fifty(history, store):
    interaction, messages, _ = history(120)

    await backfill_releases.callback(interaction, "2025-12-01")

    assert BACKFILL_BATCH_SIZE == 50
    assert [len(call.args[0]) for call in store.await_args_list] == [50, 50, 20]
    assert [m for call in store.await_args_list for m in call.args[0]] == messages       # in order, none lost


async def test_an_exact_multiple_of_the_batch_size_has_no_empty_final_batch(history, store):
    interaction, _, _ = history(100)

    await backfill_releases.callback(interaction, "2025-12-01")

    assert [len(call.args[0]) for call in store.await_args_list] == [50, 50]


async def test_reports_how_many_messages_were_scanned(history):
    interaction, _, _ = history(120)

    await backfill_releases.callback(interaction, "2025-12-01")

    [reply] = interaction.sent
    assert reply.via == "followup"
    assert reply.content == "✅ **Backfill complete!** Scanned 120 messages since 2025-12-01 00:00:00+00:00."


async def test_an_empty_history_is_a_successful_backfill_of_nothing(history, store):
    interaction, _, _ = history(0)

    await backfill_releases.callback(interaction, "2025-12-01")

    store.assert_not_awaited()
    assert "Scanned 0 messages" in interaction.sent[0].content


async def test_a_failure_part_way_is_reported_and_logged(history, store, caplog):
    interaction, _, _ = history(120)
    store.side_effect = [None, RuntimeError("YouTube is down")]

    with caplog.at_level(logging.ERROR, logger="iu-bot"):
        await backfill_releases.callback(interaction, "2025-12-01")

    assert interaction.sent[0].content == "❌ An error occurred during backfill: YouTube is down"
    assert "Error during backfill: YouTube is down" in caplog.text
