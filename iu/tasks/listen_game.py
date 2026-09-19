"""A task to send automated reminders for the listen game"""

import logging
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import tasks

from config import Channel
from db.listen_game import (
    PendingPlayer, close_round_db, get_expired_rounds_db, get_missing_players_for_reminders_db,
    get_revealing_round_ids_db, update_last_reminded_db
)
from services.listen_game import playlist_link, send_dm
from services.listen_game_reveal import start_reveal
from tasks.common import keep_running
from utils.timestamps import parse_db_timestamp

logger = logging.getLogger('iu-bot')

FIRST_REMINDER_AFTER = timedelta(hours=48)
REMINDER_EVERY = timedelta(hours=24)

@tasks.loop(hours=1)
@keep_running
async def check_listen_game_reminders(client: discord.Client, guild_id:int):
    logger.debug("Running listen game background checks...")
    if not guild_id:
        logger.error("guild_id is not set.")
        return

    guild = client.get_guild(guild_id)
    if not guild:
        logger.error("Could not find guild with ID: %s", guild_id)
        return

    channel = discord.utils.get(guild.text_channels, name=Channel.LISTEN_GAME)
    if not channel:
        logger.error("Could not find #listen-game channel.")
        return

    _resume_interrupted_reveals(channel)
    await _close_timed_out_rounds(client)
    await _send_reminders(client, channel)


def _resume_interrupted_reveals(channel: discord.TextChannel):
    """Resumes any reveal that was interrupted (e.g. by a bot restart)."""
    for revealing_round_id in get_revealing_round_ids_db():
        if start_reveal(channel, revealing_round_id):
            logger.info("Resuming the reveal for round %s.", revealing_round_id)


async def _close_timed_out_rounds(client: discord.Client):
    """Locks rounds whose deadline has passed and tells their listener."""
    for expired_round in get_expired_rounds_db():
        logger.info("Round %s has timed out! Closing submissions.", expired_round.round_id)

        # Lock the round so /listen-game-submit-song stops working
        if close_round_db(expired_round.round_id):
            # A failed DM (closed DMs, deleted account) must not stop the other rounds or the reminders
            await send_dm(
                client, expired_round.host_id,
                "⏰ **Time's Up!**\n\n"
                "The automated deadline for your Listen Game round has passed. "
                "Submissions are now locked!\n\n"
                f"Here is your generated playlist with the songs submitted so far: "
                f"{playlist_link(expired_round.playlist_id)}\n\n"
                "When you've decided your rankings, run `/listen-game-submit-ranking` in the channel!"
            )


def _reminder_due(player: PendingPlayer, now: datetime) -> bool:
    """A player is reminded once the round is 48 hours old, and then once a day until they submit."""
    if now - parse_db_timestamp(player.started_at) < FIRST_REMINDER_AFTER:
        return False
    if not player.last_reminded_at:
        return True
    return now - parse_db_timestamp(player.last_reminded_at) >= REMINDER_EVERY


async def _send_reminders(client: discord.Client, channel: discord.TextChannel):
    """DMs the players who still owe a song for the open round."""
    now = datetime.now(timezone.utc)
    for player in get_missing_players_for_reminders_db():
        if not _reminder_due(player, now):
            continue

        logger.info("Preparing to send reminder to user: %s for game: %s", player.user_id, player.game_id)
        deadline_text = ""
        if player.max_round_days:
            deadline_ts = int((parse_db_timestamp(player.started_at) + timedelta(days=player.max_round_days))
                              .timestamp())
            deadline_text = f"\n\n⏰ **Automated Deadline:** <t:{deadline_ts}:R> (<t:{deadline_ts}:f>)"

        if player.ruleset_message_id:
            link_text = f"https://discord.com/channels/{channel.guild.id}/{channel.id}/{player.ruleset_message_id}"
        else:
            link_text = f"the ruleset in **[#listen-game](<{channel.jump_url}>)**"

        sent = await send_dm(
            client, player.user_id,
            "🎧 **Listen Game Reminder!**\n\n"
            "It's been over 48 hours since the current round started, "
            "and you haven't submitted your song yet!\n"
            f"Please review the ruleset in {link_text} and use `/listen-game-submit-song` "
            f"when you are ready.{deadline_text}"
        )
        if sent:
            update_last_reminded_db(player.game_id, player.user_id)
            logger.info("Successfully sent reminder to user: %s", player.user_id)
