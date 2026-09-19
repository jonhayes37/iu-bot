"""Shared error handling for slash commands and interactive components (buttons, menus, forms)."""

import functools
import logging
import sqlite3

import discord

from db.errors import InvalidStateError
from utils.discord_files import text_file

logger = logging.getLogger('iu-bot')

GENERIC_ERROR = "❌ An unexpected error occurred while running this command."
STATE_CHANGED = (
    "⚠️ That's no longer possible: things have moved on since you started, so nothing was changed. "
    "Check where the game is now and try again."
)
DATABASE_ERROR = (
    "❌ Something went wrong saving to the database, so nothing was changed. "
    "Please try again, and let an admin know if it keeps happening."
)


async def report_interaction_error(interaction: discord.Interaction, error: Exception,
                                   keep_text: dict[str, str] | None = None):
    """
    Logs an error (with its traceback) and tells the user something went wrong. This is the one
    place database failures are reported; db/ functions raise instead of swallowing them.

    keep_text is for forms: text the user typed ({file name: text}), attached to the reply so a
    failure never costs them what they wrote.
    """
    original = getattr(error, "original", error)  # discord.py wraps command errors in CommandInvokeError
    if isinstance(original, InvalidStateError):
        logger.warning("Refused a change that no longer applies: %s", original)
        text = STATE_CHANGED
    elif isinstance(original, sqlite3.Error):
        logger.error("Database error while handling an interaction: %s", original, exc_info=original)
        text = DATABASE_ERROR
    else:
        logger.error("Unexpected error while handling an interaction: %s", original, exc_info=original)
        text = GENERIC_ERROR

    files = [text_file(content, name) for name, content in (keep_text or {}).items() if content.strip()]
    if files:
        text += "\nWhat you typed is attached so you don't lose it."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, files=files, ephemeral=True)
        else:
            await interaction.response.send_message(text, files=files, ephemeral=True)
    except discord.HTTPException as ex:
        logger.warning("Could not tell the user about an error: %s", ex)


class SafeView(discord.ui.View):
    """A view whose button, menu and timeout errors are logged and reported to the user."""

    # pylint: disable=arguments-differ,unused-argument
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        await report_interaction_error(interaction, error)


class SafeModal(discord.ui.Modal):
    """A form whose submit errors are logged and reported to the user."""

    # pylint: disable=arguments-differ
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await report_interaction_error(interaction, error)


def reports_errors(callback):
    """
    For a DynamicItem's callback: reports an error to the user like SafeView does. discord.py only
    logs errors raised by a dynamic item and drops them, so without this the user sees "interaction failed".
    """
    @functools.wraps(callback)
    async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
        try:
            return await callback(self, interaction, *args, **kwargs)
        except Exception as error:
            await report_interaction_error(interaction, error)
            return None

    return wrapper
