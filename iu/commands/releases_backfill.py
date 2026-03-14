"""Command to backfill releases from a channel's history starting from a specified date."""
import logging
from datetime import datetime, timezone
import discord
from triggers.releases import store_new_release

logger = logging.getLogger('iu-bot')

async def backfill_releases(interaction: discord.Interaction, channel: discord.TextChannel, start_date_str: str):
    """Scans the channel history from a given YYYY-MM-DD date to now and processes releases."""

    try:
        # Convert string to datetime and make it UTC aware to match Discord's internal timestamps
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        await interaction.response.send_message(
            "❌ Invalid date format. Please use YYYY-MM-DD (e.g., 2025-12-01).", 
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)

    logger.info("Starting backfill for %s since %s", channel.name, start_date_str)
    messages_scanned = 0
    try:
        async for message in channel.history(limit=None, oldest_first=True, after=start_date):
            messages_scanned += 1
            await store_new_release(message)

        await interaction.followup.send(
            f"✅ **Backfill complete!** Scanned {messages_scanned} messages since {start_date_str}."
        )

    except Exception as e:
        logger.error("Error during backfill: %s", e)
        await interaction.followup.send(f"❌ An error occurred during backfill: {e}")
