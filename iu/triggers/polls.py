"""Handles votes on the tournament polls."""

import asyncio
import logging

import discord

from config import Channel
from db.tournaments import process_user_vote, remove_user_vote

logger = logging.getLogger('iu-bot')


def _is_other_channel(client: discord.Client, channel_id: int) -> bool:
    """True if the poll is somewhere other than #tournaments. An uncached channel gets the benefit of the doubt."""
    channel = client.get_channel(channel_id)
    return channel is not None and getattr(channel, 'name', None) != Channel.TOURNAMENTS


async def handle_poll_vote(client: discord.Client, payload: discord.RawPollVoteActionEvent):
    """Records a poll vote and rewards a heart for voting in every matchup of a round."""
    # Ignore the bot's own interactions to prevent infinite loops
    if payload.user_id == client.user.id:
        return

    # Only tournament polls matter; this event fires for every poll in the server
    if _is_other_channel(client, payload.channel_id):
        return

    # This fires on every poll click, so the blocking sqlite work runs in a thread rather than
    # stalling the event loop. The vote is saved first; the reward is a separate all-or-nothing
    # payment, so if it fails the vote is kept and the next vote tries the payment again.
    reward = await asyncio.to_thread(
        process_user_vote,
        message_id=payload.message_id,
        user_id=payload.user_id,
        answer_id=payload.answer_id
    )

    if reward:
        await _announce_reward(client, payload, reward.round_num, reward.tournament_name)


async def _announce_reward(client: discord.Client, payload: discord.RawPollVoteActionEvent, r_num: int, t_name: str):
    guild = client.get_guild(payload.guild_id)
    if not guild:
        return

    news_channel = discord.utils.get(guild.text_channels, name=Channel.DISPATCH_NEWS)
    if not news_channel:
        return

    # Fall back to a plain mention if the member has left the server
    try:
        mention = (await guild.fetch_member(payload.user_id)).mention
    except discord.NotFound:
        mention = f"<@{payload.user_id}>"

    try:
        await news_channel.send(
            f"{mention} earned 1 heart for voting in every single matchup for round {r_num} of **{t_name}**!"
        )
    except discord.HTTPException as ex:
        logger.warning("Could not announce the voting reward in #dispatch-news: %s", ex)


async def handle_poll_vote_remove(client: discord.Client, payload: discord.RawPollVoteActionEvent):
    """Forgets a vote the user took back, so it no longer counts towards rewards or the raffle."""
    if payload.user_id == client.user.id or _is_other_channel(client, payload.channel_id):
        return

    await asyncio.to_thread(
        remove_user_vote,
        message_id=payload.message_id,
        user_id=payload.user_id,
        answer_id=payload.answer_id
    )
