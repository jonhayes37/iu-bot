"""Finds every slash command defined in the commands package, so none can be forgotten."""

import importlib
import pkgutil

from discord import app_commands

import commands


def all_commands() -> list[app_commands.Command | app_commands.Group]:
    """Every top-level slash command or group defined in a commands/ module."""
    found = {}
    for module_info in pkgutil.iter_modules(commands.__path__):
        if module_info.name == "registry":
            continue

        module = importlib.import_module(f"{commands.__name__}.{module_info.name}")
        for obj in vars(module).values():
            is_command = isinstance(obj, (app_commands.Command, app_commands.Group))
            # Commands added to a group with @group.command have a parent and are registered with it
            if is_command and obj.parent is None:
                found[id(obj)] = obj

    return list(found.values())
