"""Tests for main.py: what happens when the bot process starts."""

import logging
import signal
import socket
from unittest import mock

import pytest

import main as main_module


@pytest.fixture(name="process")
def _process(monkeypatch):
    """Replaces everything main() does to the outside world, recording the order of the calls."""
    calls = mock.Mock()
    monkeypatch.setattr(main_module.logging, "basicConfig", calls.basic_config)
    monkeypatch.setattr(main_module.signal, "signal", calls.signal)
    monkeypatch.setattr(main_module, "initialize_databases", calls.initialize)
    monkeypatch.setattr(main_module, "wait_for_network", calls.wait_for_network)
    monkeypatch.setattr(main_module, "IUBot", calls.bot_class)
    monkeypatch.setattr(main_module, "discord_token", lambda: "the-token")
    return calls


def test_the_databases_are_set_up_before_the_bot_runs(process):
    main_module.main()

    names = [call[0] for call in process.mock_calls]
    assert names.index("initialize") < names.index("bot_class().run")


def test_the_bot_runs_with_the_token_from_the_environment(process):
    main_module.main()

    process.bot_class.return_value.run.assert_called_once_with("the-token")


def test_logging_uses_the_configured_level(process, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    main_module.main()

    process.basic_config.assert_called_once_with(level="DEBUG")


def test_logging_defaults_to_info(process):
    main_module.main()

    process.basic_config.assert_called_once_with(level="INFO")


def test_docker_stop_shuts_the_bot_down_gracefully(process, monkeypatch):
    raise_signal = mock.Mock()
    monkeypatch.setattr(main_module.signal, "raise_signal", raise_signal)
    main_module.main()

    signum, handler = process.signal.call_args.args
    assert signum == signal.SIGTERM
    handler(signal.SIGTERM, None)

    raise_signal.assert_called_once_with(signal.SIGINT)      # the same clean shutdown as Ctrl+C


def test_a_database_that_cannot_be_prepared_stops_the_bot_before_it_connects(process):
    process.initialize.side_effect = OSError("disk full")

    with pytest.raises(OSError):
        main_module.main()

    process.bot_class.return_value.run.assert_not_called()


def test_the_bot_waits_for_the_network_after_the_databases_and_before_connecting(process):
    main_module.main()

    names = [call[0] for call in process.mock_calls]
    assert names.index("initialize") < names.index("wait_for_network") < names.index("bot_class().run")


def test_docker_stop_while_waiting_for_the_network_exits_without_connecting(process):
    process.wait_for_network.side_effect = KeyboardInterrupt

    main_module.main()

    process.bot_class.return_value.run.assert_not_called()


def _lookups(*outcomes):
    """A getaddrinfo that fails with each exception given, in turn, and then succeeds."""
    return mock.Mock(side_effect=[*outcomes, [("address",)]])


@pytest.fixture(name="sleep")
def _sleep(monkeypatch):
    sleep = mock.Mock()
    monkeypatch.setattr(main_module.time, "sleep", sleep)
    return sleep


def test_waiting_for_the_network_returns_at_once_when_discord_can_be_looked_up(monkeypatch, sleep, caplog):
    lookup = _lookups()
    monkeypatch.setattr(main_module.socket, "getaddrinfo", lookup)

    with caplog.at_level(logging.INFO):
        main_module.wait_for_network()

    lookup.assert_called_once_with("discord.com", 443)
    sleep.assert_not_called()
    assert not caplog.records


def test_waiting_for_the_network_retries_with_a_growing_delay_until_discord_can_be_looked_up(
        monkeypatch, sleep, caplog):
    failure = socket.gaierror(-3, "Temporary failure in name resolution")
    monkeypatch.setattr(main_module.socket, "getaddrinfo", _lookups(*[failure] * 6))

    with caplog.at_level(logging.INFO):
        main_module.wait_for_network()

    assert [call.args[0] for call in sleep.call_args_list] == [5, 10, 20, 40, 60, 60]
    assert sum(record.levelno == logging.WARNING for record in caplog.records) == 6
    assert "Temporary failure in name resolution" in caplog.records[0].getMessage()
    assert caplog.records[-1].getMessage() == "The network is up; connecting to Discord."


def test_waiting_for_the_network_does_not_hide_other_errors(monkeypatch, sleep):
    monkeypatch.setattr(main_module.socket, "getaddrinfo", mock.Mock(side_effect=ValueError("bad port")))

    with pytest.raises(ValueError):
        main_module.wait_for_network()

    sleep.assert_not_called()
