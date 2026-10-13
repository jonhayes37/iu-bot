"""Keeps IU's "Listening to" status in step with the saved one, so a status goes away when it expires."""

import asyncio
import logging

import discord
from discord.ext import tasks

from db.bot import get_active_bot_status_db
from tasks.common import keep_running

logger = logging.getLogger('iu-bot')


async def show_saved_status(client: discord.Client):
    """Shows the saved status as "Listening to ...", or no status if there is none or it has expired."""
    status_text = await asyncio.to_thread(get_active_bot_status_db)
    activity = discord.Activity(type=discord.ActivityType.listening, name=status_text) if status_text else None
    await client.change_presence(status=discord.Status.online, activity=activity)


@tasks.loop(hours=1)
@keep_running
async def refresh_status(client: discord.Client):
    """
    Reapplies the saved status every hour. The expiry is only checked when the status is read, so
    without this a status would stay up past its expiry until the bot next reconnected.
    """
    logger.debug("Refreshing the status.")
    await show_saved_status(client)
