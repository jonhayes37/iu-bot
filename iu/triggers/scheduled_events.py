"""Functions for scheduled events"""
import re
import datetime
import logging
import discord

logger = logging.getLogger('iu-bot')

# Regex to match the "[...]" prefix and capture the rest of the description
PREFIX_REGEX = re.compile(r'^\[(.*?)\]\s*(.*)', re.DOTALL)

# Flexible regexes to catch hours and minutes (e.g. "1 hour", "45 mins", "1h 30m")
HOURS_REGEX = re.compile(r'(\d+)\s*h', re.IGNORECASE)
MINUTES_REGEX = re.compile(r'(\d+)\s*m', re.IGNORECASE)

async def process_event(event: discord.ScheduledEvent, is_update: bool):
    """Shared logic for processing scheduled events."""
    needs_update = False
    updated_description = event.description
    new_end_time = event.end_time

    # Check for the duration prefix
    if event.description:
        match = PREFIX_REGEX.match(event.description)
        if match:
            duration_str = match.group(1)
            rest_of_desc = match.group(2)

            duration_delta = _parse_duration(duration_str)
            if duration_delta:
                # Calculate the new end time and strip the prefix
                new_end_time = event.start_time + duration_delta
                updated_description = rest_of_desc
                needs_update = True

    # If we parsed a duration, update the event natively
    if needs_update:
        try:
            await event.edit(
                description=updated_description,
                end_time=new_end_time,
                reason="Parsed and enforced duration prefix from description."
            )
            logger.info("Updated event '%s' with parsed duration.", event.name)
        except discord.Forbidden:
            logger.warning("Bot lacks 'Manage Events' permission to update duration.")
        except discord.HTTPException as ex:
            logger.error("Failed to update event duration: %s", ex)

    # Only announce if it's a new event creation
    if not is_update:
        channel = discord.utils.get(event.guild.text_channels, name='community-events')
        if not channel:
            logger.error("Could not find #community-events channel.")
            return

        role = discord.utils.get(event.guild.roles, name='Watch Parties')
        if not role:
            logger.error("Could not find Watch Parties role.")
            return

        await channel.send(
            f"{role.mention} **{event.name}** has been scheduled by {event.creator.mention}! "
            f"RSVP below so you don't miss out!\n\n{event.url}"
        )

def _parse_duration(duration_str: str) -> datetime.timedelta | None:
    """Extracts hours and minutes from a string and returns a timedelta."""
    hours, minutes = 0, 0

    h_match = HOURS_REGEX.search(duration_str)
    if h_match:
        hours = int(h_match.group(1))

    m_match = MINUTES_REGEX.search(duration_str)
    if m_match:
        minutes = int(m_match.group(1))

    if hours == 0 and minutes == 0:
        return None

    return datetime.timedelta(hours=hours, minutes=minutes)
