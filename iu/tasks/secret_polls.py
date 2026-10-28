"""Closes secret polls when their time is up and sends the results to the admin who started them."""

import logging
from datetime import datetime, timezone

import discord
from discord.ext import tasks

from db.bot import (
    SecretPoll, get_due_secret_polls, get_secret_poll, get_secret_poll_counts, get_secret_poll_options,
    mark_secret_poll_closed
)
from tasks.common import keep_running
from ui.secret_poll import SecretPollView, poll_embed, results_text

logger = logging.getLogger('iu-bot')


async def _grey_out_post(client: discord.Client, poll: SecretPoll):
    """Edits the public post to say voting has closed, with its buttons greyed out."""
    channel = client.get_channel(poll.channel_id)
    if channel is None or poll.message_id is None:
        logger.warning("Secret poll %s: its post is gone, so it can't be marked closed.", poll.poll_id)
        return
    try:
        message = await channel.fetch_message(poll.message_id)
        await message.edit(embed=poll_embed(poll.title, poll.closes_at, closed=True),
                           view=SecretPollView(poll.poll_id, get_secret_poll_options(poll.poll_id), closed=True))
    except discord.HTTPException as ex:
        logger.warning("Secret poll %s: could not mark the post closed: %s", poll.poll_id, ex)


async def _send_results(client: discord.Client, poll: SecretPoll):
    """DMs the results to the admin who started the poll. If that fails, /secret-poll-results still has them."""
    try:
        admin = client.get_user(poll.created_by) or await client.fetch_user(poll.created_by)
        await admin.send(results_text(poll, get_secret_poll_counts(poll.poll_id)))
    except discord.HTTPException as ex:
        logger.warning("Secret poll %s: could not DM the results to %s: %s", poll.poll_id, poll.created_by, ex)


async def close_secret_poll(client: discord.Client, poll: SecretPoll):
    """Closes one poll (once only), then updates its post and sends the results."""
    if not mark_secret_poll_closed(poll.poll_id):
        return
    poll = get_secret_poll(poll.poll_id)
    logger.info("Closed secret poll %s (%s).", poll.poll_id, poll.title)
    await _grey_out_post(client, poll)
    await _send_results(client, poll)


@tasks.loop(minutes=1)
@keep_running
async def close_secret_polls(client: discord.Client):
    """Closes every secret poll whose time is up. One failing poll doesn't hold up the others."""
    logger.debug("Checking for secret polls to close.")
    for poll in get_due_secret_polls(datetime.now(timezone.utc)):
        try:
            await close_secret_poll(client, poll)
        except Exception:
            logger.exception("Secret poll %s: failed to close.", poll.poll_id)
