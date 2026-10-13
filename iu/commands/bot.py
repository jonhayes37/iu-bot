"""Bot management commands"""

import typing

import discord
from discord import app_commands
from config import Channel
from db.bot import save_bot_status_db
from tasks.status import show_saved_status
from utils.validation import admin_only, validate_channel

# Discord shows at most 128 characters of an activity's name
MAX_STATUS_LENGTH = 128
MAX_STATUS_DAYS = 365


@app_commands.command(name='set-status', description="[Admin] Change IU's status message.")
@app_commands.describe(
    status_text="The text to display after \"Listening to\" (leave it out to clear the status)",
    days="How many days until this status expires (Default: 7)"
)
@admin_only
async def set_iu_status(interaction: discord.Interaction,
                        status_text: typing.Optional[app_commands.Range[str, 1, MAX_STATUS_LENGTH]] = None,
                        days: app_commands.Range[int, 1, MAX_STATUS_DAYS] = 7):
    """Changes the bot's status and saves it for reconnections."""

    restricted = await validate_channel(interaction, Channel.SANDBOX)
    if restricted:
        return

    # Saved before it is shown, so a clear (saved as empty text) also survives a reconnect
    save_bot_status_db(status_text or "", days)
    await show_saved_status(interaction.client)

    if status_text:
        await interaction.response.send_message(
            f"✅ IU's status has been updated to `{status_text}` and will expire in {days} days."
        )
    else:
        await interaction.response.send_message("✅ IU's status has been cleared!")
