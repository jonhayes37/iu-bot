"""A task that proves the bot is alive, for the container's healthcheck."""

import asyncio
import logging

import discord
from discord.ext import tasks

from config import heartbeat_path
from tasks.common import keep_running

logger = logging.getLogger('iu-bot')


@tasks.loop(minutes=1)
@keep_running
async def write_heartbeat(client: discord.Client):
    """
    Touches the heartbeat file while the bot is connected to Discord.

    The Docker healthcheck (see the Dockerfile) marks the container unhealthy when the file goes stale.
    Because this runs on the event loop, a hung loop stops the beat; it also stops while the gateway
    is disconnected, which discord.py normally repairs within seconds.
    """
    if not client.is_ready():
        logger.debug("Not connected; skipping the heartbeat.")
        return
    await asyncio.to_thread(heartbeat_path().touch)
    logger.debug("Heartbeat written.")
