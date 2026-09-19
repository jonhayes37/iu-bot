"""Handles votes on the tournament polls."""

import asyncio

import discord

from config import Channel
from db.merch import modify_db_balance
from db.tournaments import process_user_vote


async def handle_poll_vote(client: discord.Client, payload: discord.RawPollVoteActionEvent):
    """Records a poll vote and rewards a heart for voting in every matchup of a round."""
    # Ignore the bot's own interactions to prevent infinite loops
    if payload.user_id == client.user.id:
        return

    # Save the vote and check the ledger. This fires on every poll click, so the
    # blocking sqlite work runs in a thread rather than stalling the event loop.
    reward_data = await asyncio.to_thread(
        process_user_vote,
        message_id=payload.message_id,
        user_id=payload.user_id,
        answer_id=payload.answer_id
    )

    # If reward_data exists, they successfully completed the round
    if reward_data:
        t_name = reward_data['tournament_name']
        r_num = reward_data['round_num']

        # Award the heart
        await asyncio.to_thread(
            modify_db_balance,
            "IU bot",
            payload.user_id,
            1,
            f"Voted in every matchup for round {r_num} of **{t_name}**"
        )

        # Post to #dispatch-news
        guild = client.get_guild(payload.guild_id)
        if not guild:
            return

        news_channel = discord.utils.get(guild.text_channels, name=Channel.DISPATCH_NEWS)
        if news_channel:
            # Safely fetch the member to ping them
            member = await guild.fetch_member(payload.user_id)

            msg = (
                f"{member.mention} earned 1 heart for voting in every single "
                f"matchup for round {r_num} of **{t_name}**!"
            )
            await news_channel.send(msg)
