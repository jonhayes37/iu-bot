"""Tests for tasks/heartbeat.py"""

import os
from unittest import mock

import pytest

from config import heartbeat_path
from tasks.heartbeat import write_heartbeat


@pytest.fixture(name="beat_file")
def _beat_file(tmp_path, monkeypatch):
    path = tmp_path / "heartbeat"
    monkeypatch.setenv("HEARTBEAT_PATH", str(path))
    return path


async def test_a_connected_bot_writes_the_heartbeat(beat_file):
    client = mock.Mock()
    client.is_ready.return_value = True

    await write_heartbeat.coro(client)

    assert beat_file.exists()


async def test_a_disconnected_bot_does_not_write_the_heartbeat(beat_file):
    client = mock.Mock()
    client.is_ready.return_value = False

    await write_heartbeat.coro(client)

    assert not beat_file.exists()


async def test_the_next_beat_refreshes_the_file(beat_file):
    client = mock.Mock()
    client.is_ready.return_value = True
    beat_file.touch()
    os.utime(beat_file, (0, 0))

    await write_heartbeat.coro(client)

    assert beat_file.stat().st_mtime > 0


def test_the_heartbeat_path_can_be_set_and_has_a_default(monkeypatch, tmp_path):
    monkeypatch.delenv("HEARTBEAT_PATH", raising=False)
    assert heartbeat_path().name == "iu-bot-heartbeat"

    monkeypatch.setenv("HEARTBEAT_PATH", str(tmp_path / "x"))
    assert heartbeat_path() == tmp_path / "x"
