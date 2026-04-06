"""Bot management commands"""

import discord
from discord import app_commands
from db.bot import save_bot_status_db
from utils.validation import validate_channel

@app_commands.command(name='set-status', description="[Admin] Change IU's status message.")
@app_commands.describe(
    status_text="The text to display (leave blank to clear)",
    days="How many days until this status expires (Default: 7)"
)
@app_commands.default_permissions(administrator=True)
async def set_iu_status(interaction: discord.Interaction, status_text: str, days: int = 7):
    """Changes the bot's status and saves it for reconnections."""

    validate_channel(interaction, 'sandbox')

    # Save to the database
    success = save_bot_status_db(status_text, days)
    if not success:
        await interaction.response.send_message("❌ Database error: Could not save the status.", ephemeral=True)
        return

    # Update the active presence
    if status_text == "":
        await interaction.client.change_presence(status=discord.Status.online, activity=None)
        await interaction.response.send_message("✅ IU's status has been cleared!")
    else:
        activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
        await interaction.client.change_presence(status=discord.Status.online, activity=activity)
        await interaction.response.send_message(
            f"✅ IU's status has been updated to `{status_text}` and will expire in {days} days."
        )
