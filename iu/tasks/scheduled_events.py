"""A task to enhance Discord scheduled events"""

import os
import logging
from datetime import timedelta
import discord
from discord.ext import tasks
from discord.utils import utcnow

logger = logging.getLogger('iu-bot')

notified_events = set()

@tasks.loop(minutes=1)
async def check_upcoming_events(client: discord.Client, guild_id: int):
    logger.info("Running scheduled event check...")
    if not guild_id:
        logger.error("guild_id is not set.")
        return

    guild = client.get_guild(guild_id)
    if not guild:
        logger.error("Could not find guild with ID: %s", guild_id)
        return

    # Find your specific events channel
    channel = discord.utils.get(guild.text_channels, name='community-events')
    if not channel:
        logger.error("Could not find #community-events channel.")
        return

    now = utcnow()

    logger.info("Checking for upcoming events in guild: %s", guild.name)
    for event in guild.scheduled_events:
        logger.info("Handling event %s: status %s", event.name, event.status)
        if event.status != discord.EventStatus.scheduled:
            continue

        if event.id in notified_events:
            continue

        time_until_start = event.start_time - now
        if time_until_start <= timedelta(minutes=15):
            try:
                attendees = [user async for user in event.users(limit=50)]
                logger.info("Found %d attendees for event: %s", len(attendees), event.name)
                mentions = " ".join([user.mention for user in attendees if not user.bot])
                logger.info("Mentions: %s", mentions)
                if not mentions:
                    continue

                # Create the thread. Discord limits thread names to 100 characters
                thread_name = event.name if len(event.name) <= 100 else event.name[:97] + "..."
                thread = await channel.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=1440 # Archives after 24h
                )

                # Post the notification and the mentions
                msg = f"**{event.name}** is starting soon!\n\n{mentions}"
                gif_path = "iu/media/gifs/iu_event_thread.gif"
                if os.path.exists(gif_path):
                    await thread.send(content=msg, file=discord.File(gif_path))
                else:
                    logger.warning("Event GIF not found at %s. Sending text-only warning.", gif_path)
                    await thread.send(content=msg)

                notified_events.add(event.id)
                logger.info("Sent 15-minute warning for event: %s", event.name)

            except discord.Forbidden:
                logger.error("Bot lacks permissions to create threads or mention users.")
            except Exception as ex:
                logger.error("Failed to process event warning for %s: %s", event.name, ex)
