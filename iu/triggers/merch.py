"""Reaction rewards: the daily heart and the 5-reaction milestone."""

import asyncio
import collections

import discord

from config import Channel, HEART_EMOJI_NAMES
from db.merch import is_milestone_paid, process_daily_heart, process_milestone_award

MILESTONE_REACTIONS = 5
_REMEMBERED_MESSAGES = 2000

# What we've learned about messages that aren't in discord.py's message cache, so a busy old message
# doesn't cost a fetch per reaction. Both are bounded.
_reaction_totals: collections.OrderedDict[int, int] = collections.OrderedDict()
_paid_milestones: collections.OrderedDict[int, bool] = collections.OrderedDict()


def _remember(cache: collections.OrderedDict, key: int, value):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _REMEMBERED_MESSAGES:
        cache.popitem(last=False)


async def _fetch_message(client: discord.Client, payload) -> discord.Message | None:
    channel = client.get_channel(payload.channel_id)
    if not channel:
        return None
    try:
        return await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return None


# Handle emoji reactions
async def handle_reaction_add(payload, client):
    """
    Called for every reaction in the server, so it avoids network requests where it can: the heart
    reward needs only what the event already carries, and reaction counts come from discord.py's
    message cache. A message is only fetched when the cache doesn't have it.
    """
    if payload.guild_id is None or (payload.member and payload.member.bot):
        return

    guild = client.get_guild(payload.guild_id)
    if not guild:
        return

    dispatch_channel = discord.utils.get(guild.text_channels, name=Channel.DISPATCH_NEWS)
    jump_url = f"https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id}"
    message = discord.utils.get(client.cached_messages, id=payload.message_id)

    # =================
    # Daily Heart Award
    # =================
    if payload.emoji.name in HEART_EMOJI_NAMES:
        receiver_id = payload.message_author_id or (message.author.id if message else None)
        if receiver_id is None:
            message = message or await _fetch_message(client, payload)
            receiver_id = message.author.id if message else None

        sender_id = payload.user_id
        if receiver_id and sender_id != receiver_id:
            given = await asyncio.to_thread(process_daily_heart, sender_id, receiver_id, jump_url)
            if given and dispatch_channel:
                await dispatch_channel.send(f"<@{sender_id}> gave <@{receiver_id}> their daily heart on {jump_url}!")

    # ==========================================
    # FEATURE 2: 5-Reaction Milestone (IU-8)
    # ==========================================
    if payload.message_id in _paid_milestones:
        return

    if message is not None:
        total_reactions = sum(r.count for r in message.reactions)
    elif payload.message_id in _reaction_totals:
        total_reactions = _reaction_totals[payload.message_id] + 1
        _remember(_reaction_totals, payload.message_id, total_reactions)
    else:
        # First time we've seen this message: fetch it once to learn its real reaction count
        message = await _fetch_message(client, payload)
        if not message:
            return
        total_reactions = sum(r.count for r in message.reactions)
        _remember(_reaction_totals, payload.message_id, total_reactions)

    if total_reactions >= MILESTONE_REACTIONS:
        await _check_milestone(message or await _fetch_message(client, payload), jump_url, dispatch_channel)


async def _check_milestone(message: discord.Message | None, jump_url: str, dispatch_channel):
    if not message:
        return

    if await asyncio.to_thread(is_milestone_paid, message.id):
        _remember(_paid_milestones, message.id, True)
        return

    # Count unique users across all emojis
    unique_users = set()
    for reaction in message.reactions:
        async for user in reaction.users():
            if not user.bot:
                unique_users.add(user.id)

    # Process payout
    if len(unique_users) >= MILESTONE_REACTIONS:
        if await asyncio.to_thread(process_milestone_award, message.id, message.author.id, jump_url):
            _remember(_paid_milestones, message.id, True)
            if dispatch_channel:
                await dispatch_channel.send(
                    f"<@{message.author.id}>'s [post]({jump_url}) "
                    "got reactions from 5 people, and earned 3 hearts!"
                )
