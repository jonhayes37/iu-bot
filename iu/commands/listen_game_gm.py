"""GM specific commands for administrating the Listen Game."""

import logging
import re
import typing

import discord
from discord import app_commands

from db.listen_game import (
    create_game_db, start_game_db,
    get_game_by_status_db, get_current_round_db, get_round_submissions_db,
    get_user_submission_db, delete_submission_db, skip_game_turn_db,
    get_game_leaderboard_db, remove_player_from_game_db, get_registered_players_db,
    is_round_complete_db, close_round_db, upsert_submission_db,
    swap_player_orders_db, get_active_gm_id
)
from services.youtube import (
    get_playlist_video_ids, add_video_to_playlist, remove_video_from_playlist,
    extract_video_id, get_video_title, QuotaExceededError
)
from ui.listen_game import JoinGameView
from utils.strings import generate_leaderboard_text
from utils.validation import validate_channel


logger = logging.getLogger('iu-bot')

@app_commands.command(name="listen-game-create", description="[GM] Open a new Listen Game for registration.")
@app_commands.describe(
    substitute_gm="The backup GM to run your turn when you are the listener.",
    max_round_days="Optional: Auto-close rounds after X days if players haven't submitted."
)
@app_commands.checks.has_role("Listen Game GM")
async def listen_game_create(interaction: discord.Interaction, substitute_gm: discord.Member,
                             max_round_days: typing.Optional[int] = None):
    restricted = await validate_channel(interaction, 'listen-game')
    if restricted:
        return

    if substitute_gm.id == interaction.user.id:
        await interaction.response.send_message("❌ The substitute GM cannot be yourself.", ephemeral=True)
        return

    game_id = create_game_db(interaction.user.id, substitute_gm.id, max_round_days)
    if not game_id:
        await interaction.response.send_message(
            "❌ There is already an active game running! Finish it before creating a new one.",
            ephemeral=True)
        return

    player_role = discord.utils.get(interaction.guild.roles, name='Listen Game Player')
    deadline_text = f"**Max Round Duration:** {max_round_days} Days" if max_round_days \
        else "**Max Round Duration:** None (GM Managed)"

    embed = discord.Embed(
        title="A New Listen Game is Starting!",
        description=f"The GM has opened registration for a new game.\n\n{deadline_text}\n\n"
            "Click the button below to secure your spot!",
        color=0x9b59b6
    )

    await interaction.response.send_message(content=player_role.mention, embed=embed, view=JoinGameView())


@app_commands.command(name="listen-game-start", description="[GM] Close registration and officially start the game.")
@app_commands.checks.has_role("Listen Game GM")
async def listen_game_start(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, 'listen-game')
    if restricted:
        return

    game = get_game_by_status_db('registration')
    if not game:
        await interaction.response.send_message("❌ Cannot find a game in the registration phase.", ephemeral=True)
        return
    game_id = game.get('game_id')

    players = get_registered_players_db(game_id)
    if len(players) < 2:
        await interaction.response.send_message(
            f"❌ You need at least 3 players to start! Currently have {len(players)}.", ephemeral=True)
        return

    # Now returns the full shuffled list of IDs
    ordered_players = start_game_db(game['game_id'])
    if not ordered_players:
        await interaction.response.send_message("❌ Failed to start the game. Check the logs.", ephemeral=True)
        return

    # Build the formatted turn order list
    turn_order_lines = []
    for i, uid in enumerate(ordered_players, start=1):
        member = interaction.guild.get_member(uid)
        name = member.mention if member else "Unknown Player"
        turn_order_lines.append(f"{i}. {name}")

    turn_order_text = "\n".join(turn_order_lines)

    embed = discord.Embed(
        title="The Listen Game has officially begun!",
        description=(
            f"Registration is closed and the turn order has been randomized!\n\n"
            f"**Turn Order:**\n{turn_order_text}\n\n"
            f"Our first listener is <@{ordered_players[0]}>! "
            "Please use `/listen-game-post-ruleset` when you are ready to post your rules for Round 1."
        ),
        color=0x2ecc71
    )

    await interaction.response.send_message(content=f"<@{ordered_players[0]}>", embed=embed)

@app_commands.command(name="listen-game-gm-sync-playlist",
                      description="[GM] Syncs DB submissions with the YouTube playlist.")
@app_commands.checks.has_role("Listen Game GM")
async def listen_game_gm_sync_playlist(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, 'listen-game')
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    game = get_game_by_status_db('playing')
    if not game:
        await interaction.followup.send("⚠️ There is no active game right now.")
        return

    active_round = get_current_round_db(game['game_id'])
    if not active_round:
        await interaction.followup.send("⚠️ Could not find an active round.")
        return

    playlist_id = active_round.get('playlist_id')
    if not playlist_id:
        await interaction.followup.send("⚠️ No YouTube playlist has been generated for this round yet.")
        return

    submissions = get_round_submissions_db(active_round['round_id'])
    if not submissions:
        await interaction.followup.send("ℹ️ There are no submissions in the database to sync.")
        return

    existing_yt_vids = get_playlist_video_ids(playlist_id)
    missing_vids = [sub for sub in submissions if sub['video_id'] not in existing_yt_vids]

    if not missing_vids:
        await interaction.followup.send("✅ The YouTube playlist is completely up to date with the database!")
        return

    added_count = 0
    failed_count = 0
    quota_hit = False

    for sub in missing_vids:
        try:
            success = add_video_to_playlist(playlist_id, sub['video_id'])
            if success:
                added_count += 1
            else:
                failed_count += 1
        except QuotaExceededError:
            quota_hit = True
            break

    msg = f"🔄 **Sync Complete!**\nAdded {added_count} missing videos to the playlist."
    if failed_count > 0:
        msg += f"\n⚠️ Failed to add {failed_count} videos (they may be private or deleted)."

    if quota_hit:
        msg += "\n\n❌ **Sync halted: YouTube API Quota Exceeded.**\nPlease run this command again tomorrow."
        await interaction.followup.send(msg)

        active_gm_id = get_active_gm_id(game, active_round)
        gm_user = interaction.client.get_user(active_gm_id) or await interaction.client.fetch_user(active_gm_id)
        if gm_user:
            try:
                await gm_user.send("🚨 **Listen Game Alert: YouTube API Quota Exceeded!**\n"
                    "The bot ran out of YouTube API quota while trying to sync the playlist. "
                    "No more songs can be added to the playlist today.\n\n"
                    "Please run `/listen-game-gm-sync-playlist` tomorrow to finish syncing."
                )
            except discord.Forbidden:
                logger.warning("Could not DM GM %s about quota limit.", gm_user)
        return

    await interaction.followup.send(msg)

@listen_game_gm_sync_playlist.error
async def sync_playlist_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message(
            "❌ You must have the 'Listen Game GM' role to use this command.", ephemeral=True)
    else:
        logger.error("Error in gm-sync-playlist: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)

@app_commands.command(name="listen-game-gm-reject-song", description="[GM] Reject a player's submission.")
@app_commands.describe(
    player="The player whose song you are rejecting.",
    reason="The reason for rejection (sent to the player)."
)
@app_commands.checks.has_role("Listen Game GM")
async def listen_game_gm_reject_song(interaction: discord.Interaction, player: discord.Member, reason: str):
    restricted = await validate_channel(interaction, 'listen-game')
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    game = get_game_by_status_db('playing')
    if not game:
        await interaction.followup.send("⚠️ There is no active game right now.")
        return

    active_round = get_current_round_db(game['game_id'])
    if not active_round:
        await interaction.followup.send("⚠️ Could not find an active round.")
        return

    if active_round['status'] != 'submitting':
        await interaction.followup.send("⚠️ Submissions are closed! You cannot reject a song at this phase.")
        return

    # Fetch the submission
    submission = get_user_submission_db(active_round['round_id'], player.id)
    if not submission:
        await interaction.followup.send(f"⚠️ {player.display_name} has not submitted a song for this round.")
        return

    # Delete from DB
    success = delete_submission_db(active_round['round_id'], player.id)
    if not success:
        await interaction.followup.send("❌ Database error: Could not remove the submission.")
        return

    # Delete from YouTube
    playlist_id = active_round.get('playlist_id')
    if playlist_id:
        yt_removed = remove_video_from_playlist(playlist_id, submission['video_id'])
        if not yt_removed:
            logger.warning("Failed to remove video %s from YT playlist during GM rejection.", submission['video_id'])

    # DM the player
    try:
        msg = (
            f"🚨 **Listen Game Update** 🚨\n\n"
            f"The Game Master has rejected your submission for the current round (`{submission['raw_title']}`).\n"
            f"**Reason:** {reason}\n\n"
            f"Please find a new track and use `/submit-song` to try again!"
        )
        await player.send(msg)
        dm_status = "Player was DMed the reason."
    except discord.Forbidden:
        dm_status = "Player has DMs disabled. You will need to ping them in the channel manually."

    # Acknowledge GM
    await interaction.followup.send(f"✅ **Success!** Removed `{submission['raw_title']}`. {dm_status}")

@listen_game_gm_reject_song.error
async def reject_song_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message("❌ You must have the 'Listen Game GM' role to use this command.",
                                                ephemeral=True)
    else:
        logger.error("Error in gm-reject-song: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)

@app_commands.command(name="listen-game-gm-skip-turn", description="[GM] Forcefully skip the current listener's turn.")
@app_commands.describe(
    player="The listener whose turn you are skipping.",
    reason="The reason for skipping (sent to the player)."
)
@app_commands.checks.has_role("Listen Game GM")
async def listen_game_gm_skip_turn(interaction: discord.Interaction, player: discord.Member, reason: str):
    restricted = await validate_channel(interaction, 'listen-game')
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    game = get_game_by_status_db('playing')
    if not game:
        await interaction.followup.send("⚠️ There is no active game right now.")
        return

    active_round = get_current_round_db(game['game_id'])
    if not active_round:
        await interaction.followup.send("⚠️ Could not find an active round.")
        return

    if active_round['host_id'] != player.id:
        current_host = interaction.guild.get_member(active_round['host_id'])
        host_name = current_host.display_name if current_host else "Unknown"
        await interaction.followup.send(
            f"❌ {player.display_name} is not the current listener. The current listener is {host_name}.")
        return

    # 1. Execute the skip
    next_host_id = skip_game_turn_db(game['game_id'], active_round['round_id'])

    # 2. DM the skipped player
    try:
        msg = (
            f"🚨 **Listen Game Update** 🚨\n\n"
            f"The Game Master has forcefully skipped your turn as listener for the current round.\n"
            f"**Reason:** {reason}\n\n"
            f"If you have questions, please reach out to the GM directly."
        )
        await player.send(msg)
        dm_status = "Player was DMed the reason."
    except discord.Forbidden:
        dm_status = "Player has DMs disabled. You will need to ping them manually."

    # Inform the GM
    await interaction.followup.send(f"✅ **Success!** {player.display_name}'s turn has been skipped. {dm_status}")

    # Announce in the game channel
    listen_channel = interaction.channel
    await listen_channel.send(
        f"⚠️ **Attention!** The Game Master has skipped <@{player.id}>'s turn."
    )

    if next_host_id:
        await listen_channel.send(
            f"⏭️ The turn order has advanced! The new listener is <@{next_host_id}>! "
            "Please use `/listen-game-post-ruleset` when you are ready.")
    else:
        await listen_channel.send("🏆 **The game has concluded early due to a turn skip! Calculating final scores...**")

        leaderboard = get_game_leaderboard_db(game['game_id'])
        if leaderboard:
            await listen_channel.send(generate_leaderboard_text(leaderboard))


@listen_game_gm_skip_turn.error
async def skip_turn_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message(
            "❌ You must have the 'Listen Game GM' role to use this command.", ephemeral=True)
    else:
        logger.error("Error in gm-skip-turn: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)

@app_commands.command(name="listen-game-gm-remove-player", description="[GM] Remove a player from the game entirely.")
@app_commands.describe(
    player="The player to remove.",
    reason="The reason for removal (sent to the player)."
)
@app_commands.checks.has_role("Listen Game GM")
async def listen_game_gm_remove_player(interaction: discord.Interaction, player: discord.Member, reason: str):
    restricted = await validate_channel(interaction, 'listen-game')
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    # Check for a playing or registering game
    game = get_game_by_status_db('playing')
    if not game:
        game = get_game_by_status_db('registration')
        if not game:
            await interaction.followup.send("⚠️ There is no active game right now.")
            return

    game_id = game['game_id']

    players = get_registered_players_db(game_id)
    if player.id not in players:
        await interaction.followup.send(f"⚠️ {player.display_name} is not in the current game.")
        return

    active_round = get_current_round_db(game_id)

    # State safety checks for active games
    if game['status'] == 'playing' and active_round:
        # Block removing the active host to prevent breaking the game state
        if active_round['host_id'] == player.id:
            await interaction.followup.send(
                f"❌ {player.display_name} is the current listener! Please use `/listen-game-gm-skip-turn` "
                "first to advance the game before removing them."
            )
            return

        # If we are in the submission phase, scrub their current submission if they made one
        # if active_round['status'] == 'submitting':
        #     submission = get_user_submission_db(active_round['round_id'], player.id)
        #     if submission:
        #         delete_submission_db(active_round['round_id'], player.id)
        #         playlist_id = active_round.get('playlist_id')
        #         if playlist_id:
        #             remove_video_from_playlist(playlist_id, submission['video_id'])

    # Perform the database removal
    success = remove_player_from_game_db(game_id, player.id)
    if not success:
        await interaction.followup.send("❌ Database error: Could not remove the player.")
        return

    # Notify the player
    try:
        msg = (
            f"🚨 **Listen Game Update** 🚨\n\n"
            f"The Game Master has removed you from the current Listen Game.\n"
            f"**Reason:** {reason}\n\n"
            f"If you have questions, please reach out to the GM directly."
        )
        await player.send(msg)
        dm_status = "Player was DMed."
    except discord.Forbidden:
        dm_status = "Player has DMs disabled."

    # Acknowledge the GM and announce in channel
    await interaction.followup.send(f"✅ **Success!** {player.display_name} has been removed from the game. {dm_status}")

    listen_channel = interaction.channel
    await listen_channel.send(f"The Game Master has removed {player.display_name} from the game.")

    # Check if removing this player caused the round to suddenly be complete!
    if game['status'] == 'playing' and active_round and active_round['status'] == 'submitting':
        if is_round_complete_db(game_id, active_round['round_id']):
            close_round_db(active_round['round_id'])

            host_user = await interaction.client.fetch_user(active_round['host_id'])
            if host_user:
                playlist_id = active_round.get('playlist_id')
                playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}" if playlist_id \
                    else "No playlist generated."

                try:
                    await host_user.send(
                        "🎉 **All submissions are in for your Listen Game round!**\n\n"
                        "A player was removed, which means everyone remaining has already submitted. "
                        "The round has been automatically closed.\n\n"
                        f"Here is your generated playlist to review: {playlist_url}\n\n"
                        "When you've decided your rankings, run `/listen-game-submit-ranking` in "
                        "the channel to start the reveal!"
                    )
                except discord.Forbidden:
                    logger.warning("Could not DM listener %s about round completion after player removal.",
                                   active_round['host_id'])

@listen_game_gm_remove_player.error
async def remove_player_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message("❌ You must have the 'Listen Game GM' role to use this command.",
                                                ephemeral=True)
    else:
        logger.error("Error in gm-remove-player: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)

@app_commands.command(name="listen-game-gm-force-start-round",
                      description="[GM] Force start ranking phase by explicitly skipping outstanding players.")
@app_commands.describe(skipped_users="Tag the exact users you are skipping (e.g., @User1 @User2).")
@app_commands.checks.has_role("Listen Game GM")
async def listen_game_gm_force_start_round(interaction: discord.Interaction, skipped_users: str):
    """
    Forcefully advances a round to the ranking phase.

    This command requires the GM to explicitly mention all players who have not yet
    submitted. If the mentions do not match the database state, the command fails.
    """
    restricted = await validate_channel(interaction, 'listen-game')
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    game = get_game_by_status_db('playing')
    if not game:
        await interaction.followup.send("⚠️ There is no active game right now.")
        return

    active_round = get_current_round_db(game['game_id'])
    if not active_round or active_round['status'] != 'submitting':
        await interaction.followup.send("⚠️ The round is not currently in the submission phase.")
        return

    # Identify missing players
    all_players = get_registered_players_db(game['game_id'])
    submissions = get_round_submissions_db(active_round['round_id'])

    submitted_ids = {sub['user_id'] for sub in submissions}
    host_id = active_round['host_id']
    outstanding_players = set(all_players) - {host_id} - submitted_ids

    # Parse and validate GM input
    parsed_ids = {int(uid) for uid in re.findall(r'<@!?(\d+)>', skipped_users)}

    if outstanding_players != parsed_ids:
        missing_mentions = " ".join([f"<@{uid}>" for uid in outstanding_players]) if outstanding_players else "No one!"
        await interaction.followup.send(
            f"❌ **Validation Failed!** Your tags do not match the outstanding players.\n\n"
            f"**Actually missing:** {missing_mentions}\n"
            f"Please run the command again and tag exactly those users."
        )
        return

    # Transition round state
    if not close_round_db(active_round['round_id']):
        await interaction.followup.send("❌ Database error: Could not close the round.")
        return

    # Update the Live Tracker Message
    if active_round.get('status_message_id'):
        try:
            tracker_msg = await interaction.channel.fetch_message(active_round['status_message_id'])
            total_needed = len(all_players) - 1
            host_mention = f"<@{host_id}>"

            tracker_text = (
                f"🎧 **Round Status:** We are at `{len(submissions)}/{total_needed}` submissions for the round.\n"
                f"⏭️ **Round forced closed by GM!** Playlist sent to {host_mention}!"
            )
            await tracker_msg.edit(content=tracker_text)
        except (discord.NotFound, discord.Forbidden):
            pass

    # Notify the Host
    host_user = interaction.client.get_user(host_id) or await interaction.client.fetch_user(host_id)
    if host_user:
        playlist_id = active_round.get('playlist_id')
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}" if playlist_id \
            else "No playlist generated."

        try:
            await host_user.send(
                "🚨 **Round Force-Closed!**\n\n"
                "The GM has manually ended the submission phase, skipping the remaining players.\n\n"
                f"Playlist: {playlist_url}\n\n"
                "Run `/listen-game-submit-ranking` in the channel to start the reveal!"
            )
            dm_status = "Listener notified via DM."
        except discord.Forbidden:
            dm_status = "Listener has DMs disabled."
    else:
        dm_status = "Could not find listener user."

    await interaction.followup.send(f"✅ **Success!** Round forced closed. {dm_status}")

@listen_game_gm_force_start_round.error
async def force_start_round_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Local error handler for the force start command."""
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message(
            "❌ You must have the 'Listen Game GM' role to use this command.", ephemeral=True)
    else:
        logger.error("Error in gm-force-start-round: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)

@app_commands.command(name="listen-game-gm-force-submit",
                      description="[GM] Bypass filters to forcefully submit a song for a player.")
@app_commands.describe(
    player="The player you are submitting for.",
    url="The YouTube link to the song."
)
@app_commands.checks.has_role("Listen Game GM")
async def listen_game_gm_force_submit(interaction: discord.Interaction, player: discord.Member, url: str):
    """
    Forcefully adds a submission for a player, bypassing fuzzy match blocks.
    Updates the live tracker and handles round completion just like a normal submission.
    """
    restricted = await validate_channel(interaction, 'listen-game')
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    game = get_game_by_status_db('playing')
    if not game:
        await interaction.followup.send("⚠️ There is no active game right now.")
        return

    active_round = get_current_round_db(game['game_id'])
    if not active_round or active_round['status'] != 'submitting':
        await interaction.followup.send("⚠️ The round is not currently in the submission phase.")
        return

    if player.id == active_round['host_id']:
        await interaction.followup.send("❌ You cannot submit a song for the current listener.")
        return

    # Extract data
    video_id = extract_video_id(url)
    if not video_id:
        await interaction.followup.send("❌ Invalid YouTube URL.")
        return

    video_title = get_video_title(video_id)
    if not video_title:
        await interaction.followup.send("❌ Could not fetch that video. It may be private or deleted.")
        return

    # Handle YouTube Playlist Swap & Addition
    user_previous_sub = get_user_submission_db(active_round['round_id'], player.id)
    playlist_id = active_round.get('playlist_id')

    try:
        if playlist_id and user_previous_sub:
            remove_video_from_playlist(playlist_id, user_previous_sub['video_id'])
        else:
            await interaction.followup.send("❌ Could not find the playlist or previous submission.")
            return

        added = add_video_to_playlist(playlist_id, video_id)
        if not added:
            await interaction.followup.send("❌ Failed to add video to the playlist. It may be blocked or private.")
            return

    except QuotaExceededError:
        # Handle YouTube Quota limits gracefully
        upsert_submission_db(active_round['round_id'], player.id, video_id, video_title)

        await interaction.followup.send(
            f"✅ **Success!** `{video_title}` accepted into the database for {player.display_name}.\n\n"
            "⚠️ *Note: YouTube API limits have been reached. "
            "Run `/listen-game-gm-sync-playlist` tomorrow to push it to the playlist.*"
        )

        try:
            await player.send(f"✅ The GM has forcefully submitted your song `{video_title}` for the Listen Game!")
        except discord.Forbidden:
            pass
        return

    # Save to Database
    upsert_submission_db(active_round['round_id'], player.id, video_id, video_title)

    # Update the Live Tracker Message
    all_players = get_registered_players_db(game['game_id'])
    total_needed = len(all_players) - 1
    current_submissions = get_round_submissions_db(active_round['round_id'])
    is_complete = is_round_complete_db(game['game_id'], active_round['round_id'])

    if active_round.get('status_message_id'):
        try:
            tracker_msg = await interaction.channel.fetch_message(active_round['status_message_id'])
            tracker_text = f"🎧 **Round Status:** We are at `{len(current_submissions)}/{total_needed}` " \
                "submissions for the round."

            if is_complete:
                host_member = interaction.guild.get_member(active_round['host_id'])
                host_mention = host_member.mention if host_member else "the listener"
                tracker_text += f"\n\n✅ **All submissions received! Playlist sent to {host_mention}!**"

            await tracker_msg.edit(content=tracker_text)
        except (discord.NotFound, discord.Forbidden):
            logger.warning("Could not update status message.")

    # Final Completion Check & DM to Host
    if not user_previous_sub and is_complete:
        close_round_db(active_round['round_id'])

        host_user = await interaction.client.fetch_user(active_round['host_id'])
        if host_user:
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            try:
                await host_user.send(
                    "🎉 **All submissions are in for your Listen Game round!**\n\n"
                    "The round has been automatically closed. Here is your generated playlist to review: "
                    f"{playlist_url}\n\nWhen you've decided your rankings, run `/listen-game-submit-ranking` "
                    "in the channel to start the reveal!"
                )
            except discord.Forbidden:
                logger.warning("Could not DM listener %s about round completion.", active_round['host_id'])

    # Notify Player & Respond to GM
    try:
        await player.send(f"✅ The GM has forcefully submitted your song `{video_title}` for the Listen Game!")
        dm_status = "Player was DMed."
    except discord.Forbidden:
        dm_status = "Player has DMs disabled."

    if user_previous_sub:
        await interaction.followup.send(
            f"🔄 **Updated!** Swapped submission to `{video_title}` for {player.display_name}. {dm_status}")
    else:
        await interaction.followup.send(
            f"✅ **Success!** `{video_title}` accepted for {player.display_name}. {dm_status}")

@listen_game_gm_force_submit.error
async def force_submit_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Local error handler for the force submit command."""
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message("❌ You must have the 'Listen Game GM' role to use this command.",
                                                ephemeral=True)
    else:
        logger.error("Error in gm-force-submit: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)

@app_commands.command(name="listen-game-gm-approve-playlist",
                      description="[GM] Approve the round's playlist and notify the listener.")
@app_commands.checks.has_role("Listen Game GM")
async def listen_game_gm_approve_playlist(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, 'listen-game')
    if restricted:
        return

    # Use ephemeral so the GM's command usage doesn't clutter the chat
    await interaction.response.defer(ephemeral=True)

    game = get_game_by_status_db('playing')
    if not game:
        await interaction.followup.send("⚠️ There is no active game right now.")
        return

    active_round = get_current_round_db(game['game_id'])
    if not active_round:
        await interaction.followup.send("⚠️ Could not find an active round.")
        return

    # Check if we are actually waiting for approval
    if active_round['status'] != 'submitting':
        await interaction.followup.send("⚠️ The round is not in the submission phase.")
        return

    if not is_round_complete_db(game['game_id'], active_round['round_id']):
        await interaction.followup.send("⚠️ Cannot approve yet! Not all players have submitted a song.")
        return

    # Close the round in the database (transitions state to 'ranking')
    success = close_round_db(active_round['round_id'])
    if not success:
        await interaction.followup.send("❌ Database error: Could not close the round.")
        return

    host_member = interaction.guild.get_member(active_round['host_id'])
    host_mention = host_member.mention if host_member else "the listener"

    # Update the Live Tracker Message in the channel
    if active_round.get('status_message_id'):
        try:
            tracker_msg = await interaction.channel.fetch_message(active_round['status_message_id'])
            all_players = get_registered_players_db(game['game_id'])
            total_needed = len(all_players) - 1
            current_submissions = get_round_submissions_db(active_round['round_id'])

            tracker_text = f"🎧 **Round Status:** We are at `{len(current_submissions)}/{total_needed}` " \
                "submissions for the round."
            tracker_text += f"\n\n✅ **All submissions received! Playlist sent to {host_mention}!**"

            await tracker_msg.edit(content=tracker_text)
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning("Failed to update status message during GM approval: %s", e)

    # DM the Host that they can begin ranking
    host_user = interaction.client.get_user(active_round['host_id']) or \
        await interaction.client.fetch_user(active_round['host_id'])
    if host_user:
        playlist_id = active_round.get('playlist_id')
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}" if playlist_id \
            else "No playlist generated."

        try:
            await host_user.send(
                "🎉 **All submissions are in for your Listen Game ruleset!**\n\n"
                f"Here is your playlist to review: {playlist_url}\n\n"
                "When you've decided your rankings, use `/listen-game-submit-ranking` in #listen-game!"
            )
            dm_status = "Listener notified via DM."
        except discord.Forbidden:
            logger.warning("Could not DM listener %s about round approval.", active_round['host_id'])
            dm_status = "Listener has DMs disabled."
    else:
        dm_status = "Could not find listener user."

    # Acknowledge the GM silently
    await interaction.followup.send(
        f"✅ **Success!** The round has been closed and the playlist sent to {host_mention}. {dm_status}")

@app_commands.command(name="listen-game-gm-swap-players",
                      description="[GM] Swap the turn order of two players who have yet to be the listener.")
@app_commands.describe(
    player1="The first player to swap.",
    player2="The second player to swap."
)
@app_commands.checks.has_role("Listen Game GM")
async def listen_game_gm_swap_players(
    interaction: discord.Interaction,
    player1: discord.Member,
    player2: discord.Member
):
    # 1. Fetch the active game instance
    game = get_game_by_status_db('playing')
    if not game:
        await interaction.response.send_message("⚠️ There is no active Listen Game currently running.",
                                                ephemeral=True)
        return

    if player1.id == player2.id:
        await interaction.response.send_message("❌ You cannot swap a player with themselves.", ephemeral=True)
        return

    # 3. Attempt the swap in the database
    result = swap_player_orders_db(game['game_id'], player1.id, player2.id)

    # 4. Respond to the GM
    if result["success"]:
        await interaction.response.send_message(
            f"🔄 {result['message']}\n"
            f"**{player1.display_name}** and **{player2.display_name}** have swapped positions in the turn order.",
            ephemeral=False
        )
    else:
        await interaction.response.send_message(result["message"], ephemeral=True)
