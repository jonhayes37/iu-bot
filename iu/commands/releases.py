"""Command to backfill releases from a channel's history starting from a specified date."""
import logging
from datetime import datetime, timezone
import discord
from config import Channel
from triggers.releases import store_new_releases

# Messages handled together, so their videos are looked up in shared YouTube requests
BACKFILL_BATCH_SIZE = 50

logger = logging.getLogger('iu-bot')

@discord.app_commands.command(name='backfill-new-releases',
                              description="[Admin] Backfills new releases from a specific date")
@discord.app_commands.describe(start_date="The start date for the backfill in YYYY-MM-DD format (e.g., 2025-12-01)")
@discord.app_commands.default_permissions(administrator=True)
async def backfill_releases(interaction: discord.Interaction, start_date: str):
    """Scans the channel history from a given YYYY-MM-DD date to now and processes releases."""
    channel = discord.utils.get(interaction.guild.text_channels, name=Channel.NEW_RELEASES)
    if not channel:
        return await interaction.response.send_message("Could not find the #new-releases channel.", ephemeral=True)

    try:
        # Convert string to datetime and make it UTC aware to match Discord's internal timestamps
        start_date = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        await interaction.response.send_message(
            "❌ Invalid date format. Please use YYYY-MM-DD (e.g., 2025-12-01).", 
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)

    logger.info("Starting backfill for %s since %s", channel.name, start_date)
    messages_scanned = 0
    batch = []
    try:
        async for message in channel.history(limit=None, oldest_first=True, after=start_date):
            messages_scanned += 1
            batch.append(message)
            if len(batch) >= BACKFILL_BATCH_SIZE:
                await store_new_releases(batch)
                batch = []

        if batch:
            await store_new_releases(batch)

        await interaction.followup.send(
            f"✅ **Backfill complete!** Scanned {messages_scanned} messages since {start_date}."
        )

    except Exception as ex:
        logger.error("Error during backfill: %s", ex)
        await interaction.followup.send(f"❌ An error occurred during backfill: {ex}")
