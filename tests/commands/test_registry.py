"""Tests for commands/registry.py, and rules every slash command has to follow."""

import pytest

from discord import app_commands

from commands.registry import all_commands

COMMANDS = all_commands()
ADMIN = [c for c in COMMANDS if c.description.startswith("[Admin")]
ROLE_RESTRICTED = [c for c in COMMANDS if c.description.startswith(("[GM]", "[Listener]"))]
OPEN_TO_ALL = [c for c in COMMANDS if c not in ADMIN]


def _name(command):
    return command.name


def test_finds_the_commands_of_every_module():
    names = {command.name for command in COMMANDS}

    assert len(COMMANDS) == len(names) == 46           # and none is registered twice
    assert {"check-balance", "draw-raffle", "my-ultimate-bias", "listen-game-start", "set-status",
            "new-tournament", "register-role", "export-lists"} <= names


def test_only_top_level_commands_are_returned():
    assert all(command.parent is None for command in COMMANDS)


def test_the_groups_of_commands_are_as_expected():
    assert len(ADMIN) > 20 and len(ROLE_RESTRICTED) > 10 and len(OPEN_TO_ALL) > 10


@pytest.mark.parametrize("command", COMMANDS, ids=_name)
def test_has_a_name_and_description_discord_accepts(command):
    assert command.name == command.name.lower() and len(command.name) <= 32
    assert 0 < len(command.description) <= 100


@pytest.mark.parametrize("command", ADMIN, ids=_name)
def test_admin_commands_are_hidden_from_others_and_checked_at_run_time(command):
    assert command.default_permissions is not None and command.default_permissions.administrator
    assert command.checks


@pytest.mark.parametrize("command", ROLE_RESTRICTED, ids=_name)
def test_commands_for_a_role_check_it_at_run_time(command):
    assert command.checks


@pytest.mark.parametrize("command", OPEN_TO_ALL, ids=_name)
def test_other_commands_have_no_default_permission_restriction(command):
    assert command.default_permissions is None


@pytest.mark.parametrize("command", [c for c in COMMANDS if isinstance(c, app_commands.Command)], ids=_name)
def test_every_option_has_a_description(command):
    # Without one, Discord shows a placeholder ("...") next to the option
    for parameter in command.parameters:
        assert parameter.description and parameter.description != "…", f"{command.name}: {parameter.name}"
        assert len(parameter.description) <= 100, f"{command.name}: {parameter.name}"      # Discord's limit
