"""Helpers for testing views, modals and buttons without Discord.

Text boxes and menus get their values from Discord when a user submits; here `fill` and `choose` set them
directly. Build views and modals inside an async test (they need a running event loop).
"""

import discord


def fill(text_input: discord.ui.TextInput, value: str) -> None:
    """Types `value` into a modal's text box, as the user would before submitting."""
    setattr(text_input, "_value", value)


def choose(select: discord.ui.Select, *values: str) -> None:
    """Picks options in a select menu, as the user would before pressing a button."""
    setattr(select, "_values", list(values))


def match_custom_id(item_class: type[discord.ui.DynamicItem], custom_id: str):
    """The regex match discord.py hands to `from_custom_id` when a button with this ID is pressed, or None."""
    return getattr(item_class, "__discord_ui_compiled_template__").fullmatch(custom_id)


def button_labels(view: discord.ui.View) -> list[str]:
    """The labels of the buttons in a view, in order (including buttons wrapped in a DynamicItem)."""
    buttons = [getattr(item, "item", item) for item in view.children]
    return [button.label for button in buttons if isinstance(button, discord.ui.Button)]


def text_input_label(text_input: discord.ui.TextInput) -> str:
    """The label shown above a modal text box."""
    return text_input.to_component_dict()["label"]
