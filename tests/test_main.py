"""Tests for main.py: what happens when the bot process starts."""

import signal
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
