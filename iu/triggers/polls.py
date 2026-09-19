"""Handles votes on the tournament polls."""

import asyncio
import logging

import discord

from config import Channel
from db.merch import award_once
from db.tournaments import mark_reward_claimed, process_user_vote, remove_user_vote

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

    # Save the vote and check the ledger. This fires on every poll click, so the
    # blocking sqlite work runs in a thread rather than stalling the event loop.
    reward_data = await asyncio.to_thread(
        process_user_vote,
        message_id=payload.message_id,
        user_id=payload.user_id,
        answer_id=payload.answer_id
    )

    # If reward_data exists, they successfully completed the round and haven't been paid for it yet
    if not reward_data:
        return

    t_name = reward_data['tournament_name']
    r_num = reward_data['round_num']

    # Pay the heart, then record that it was paid. The payment carries a marker so it can never be
    # paid twice, and if it fails nothing is recorded, so the user's next vote tries again.
    try:
        newly_paid = await asyncio.to_thread(
            award_once,
            f"[vote:{reward_data['tournament_id']}:{r_num}:{payload.user_id}]",
            "IU bot",
            payload.user_id,
            1,
            f"Voted in every matchup for round {r_num} of **{t_name}**"
        )
        await asyncio.to_thread(mark_reward_claimed, reward_data['tournament_id'], r_num, payload.user_id)
    except Exception:
        logger.exception("Could not pay the round %s voting reward to %s; it will retry on their next vote.",
                         r_num, payload.user_id)
        return

    if newly_paid:
        await _announce_reward(client, payload, r_num, t_name)


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
