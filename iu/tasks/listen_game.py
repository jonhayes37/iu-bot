"""A task to send automated reminders for the listen game"""

import logging
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import tasks

from db.listen_game import (
    get_missing_players_for_reminders_db, update_last_reminded_db, get_expired_rounds_db,
    close_round_db
)

logger = logging.getLogger('iu-bot')

@tasks.loop(hours=1)
async def check_listen_game_reminders(client: discord.Client, guild_id:int):
    logger.info("Running listen game background checks...")
    if not guild_id:
        logger.error("guild_id is not set.")
        return

    guild = client.get_guild(guild_id)
    if not guild:
        logger.error("Could not find guild with ID: %s", guild_id)
        return

    channel = discord.utils.get(guild.text_channels, name='sandbox')
    if not channel:
        logger.error("Could not find #listen-game channel.")
        return

    # ---------------------------------------------------------
    # Phase 1: Check for Timeouts
    # ---------------------------------------------------------
    expired_rounds = get_expired_rounds_db()
    for round_data in expired_rounds:
        round_id = round_data['round_id']
        host_id = round_data['host_id']
        playlist_id = round_data['playlist_id']

        logger.info("Round %s has timed out! Closing submissions.", round_id)

        # Lock the round so /submit-song stops working
        success = close_round_db(round_id)
        if success:
            host_user = client.get_user(host_id) or await client.fetch_user(host_id)
            if host_user:
                playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}" if playlist_id \
                    else "No playlist generated."
                msg = (
                    "⏰ **Time's Up!**\n\n"
                    "The automated deadline for your Listen Game round has passed. "
                    "Submissions are now locked!\n\n"
                    f"Here is your generated playlist with the songs submitted so far: {playlist_url}\n\n"
                    "When you've decided your rankings, post your results in the channel and tag the GM!"
                )
                try:
                    await host_user.send(msg)
                except discord.Forbidden:
                    logger.warning("Could not DM host %s about round timeout.", host_id)

    # ---------------------------------------------------------
    # Phase 2: Send Reminders (Only for rounds still active)
    # ---------------------------------------------------------
    missing_players = get_missing_players_for_reminders_db()
    if not missing_players:
        return

    now = datetime.now(timezone.utc)
    for row in missing_players:
        try:
            started_at = datetime.strptime(row['started_at'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            hours_since_start = (now - started_at).total_seconds() / 3600
            if hours_since_start >= 48:
                should_remind = False

                if not row['last_reminded_at']:
                    should_remind = True
                else:
                    last_reminded_dt = datetime.strptime(
                        row['last_reminded_at'],
                        "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                    hours_since_reminder = (now - last_reminded_dt).total_seconds() / 3600
                    if hours_since_reminder >= 24:
                        should_remind = True

                if should_remind:
                    logger.info("Preparing to send reminder to user: %s for game: %s", row['user_id'], row['game_id'])
                    deadline_text = ""
                    if row['max_round_days']:
                        deadline_dt = started_at + timedelta(days=row['max_round_days'])
                        deadline_ts = int(deadline_dt.timestamp())
                        deadline_text = f"\n\n⏰ **Automated Deadline:** <t:{deadline_ts}:R> (<t:{deadline_ts}:f>)"

                    msg = (
                        "🎧 **Listen Game Reminder!**\n\n"
                        "It's been over 48 hours since the current round started, "
                        "and you haven't submitted your song yet! "
                        f"Please review the theme in {channel.mention} and use `/submit-song` "
                        f"when you are ready.{deadline_text}"
                    )

                    user = client.get_user(row['user_id']) or await client.fetch_user(row['user_id'])
                    await user.send(msg)

                    update_last_reminded_db(row['game_id'], row['user_id'])
                    logger.info("Successfully sent reminder to user: %s", row['user_id'])

        except discord.Forbidden:
            logger.warning("Could not DM user %s (DMs closed).", row['user_id'])
        except Exception as ex:
            logger.error("Failed to process listen game reminder for user %s: %s", row['user_id'], ex)
