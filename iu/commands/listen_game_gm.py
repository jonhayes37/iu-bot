"""GM specific commands for administrating the Listen Game."""

import asyncio
import logging
import re
import typing

import discord
from discord import app_commands

from config import Channel, Role
from db.listen_game import (
    GameStatus, RoundStatus, Submission, SwapOutcome, close_round_db, create_game_db, delete_submission_db,
    get_active_gm_id, get_current_round_db, get_game_by_status_db, get_game_leaderboard_db, get_ordered_players_db,
    get_registered_players_db, get_round_submissions_db, get_user_submission_db, is_round_complete_db,
    remove_player_from_game_db, skip_game_turn_db, start_game_db, swap_player_orders_db, update_game_start_message_db,
    upsert_submission_db
)
from services.listen_game import playlist_link, require_active_round, send_dm, update_submission_tracker
from services.listen_game_playlist import (
    SUBMISSION_LOCK, PlaylistOutcome, get_host_name, put_song_in_round_playlist
)
from services.youtube import (
    get_playlist_video_ids, add_video_to_playlist, remove_video_from_playlist,
    extract_video_id, get_video_title, QuotaExceededError
)
from ui.listen_game import JoinGameView
from utils.strings import generate_leaderboard_text
from utils.validation import validate_channel


logger = logging.getLogger('iu-bot')

ROUND_ALREADY_MOVED_ON = "⚠️ The round has already moved on, so nothing was changed."

_SWAP_FAILURES = {
    SwapOutcome.NO_ACTIVE_HOST: "❌ Could not determine the current active host or turn order.",
    SwapOutcome.PLAYER_NOT_IN_GAME: "❌ One or both specified players are not registered in this game.",
    SwapOutcome.NOT_AFTER_HOST: "❌ Cannot swap: Both players must be scheduled *after* the current host's turn.",
}


def _turn_order_lines(guild: discord.Guild, user_ids: list[int], unknown_name: str | None = None) -> str:
    """The numbered turn order, as mentions."""
    lines = []
    for i, uid in enumerate(user_ids, start=1):
        member = guild.get_member(uid)
        name = member.mention if member else (unknown_name or f"<@{uid}>")
        lines.append(f"{i}. {name}")
    return "\n".join(lines)


@app_commands.command(name="listen-game-create", description="[GM] Open a new Listen Game for registration.")
@app_commands.describe(
    substitute_gm="The backup GM to run your turn when you are the listener.",
    max_round_days="Optional: Auto-close rounds after X days if players haven't submitted."
)
@app_commands.checks.has_role(Role.LISTEN_GAME_GM)
async def listen_game_create(interaction: discord.Interaction, substitute_gm: discord.Member,
                             max_round_days: typing.Optional[int] = None):
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
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

    player_role = discord.utils.get(interaction.guild.roles, name=Role.LISTEN_GAME_PLAYER)
    deadline_text = f"**Max Round Duration:** {max_round_days} Days" if max_round_days \
        else "**Max Round Duration:** None (GM Managed)"

    embed = discord.Embed(
        title="🎵 A New Listen Game is Starting!",
        description=f"{interaction.user.mention} has opened registration for a new game.\n\n{deadline_text}\n\n"
            "Click the button below to secure your spot!",
        color=0x9b59b6
    )

    await interaction.response.send_message(content=player_role.mention if player_role else None,
                                            embed=embed, view=JoinGameView())

@app_commands.command(name="listen-game-start", description="[GM] Close registration and officially start the game.")
@app_commands.checks.has_role(Role.LISTEN_GAME_GM)
async def listen_game_start(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    game = get_game_by_status_db(GameStatus.REGISTRATION)
    if not game:
        await interaction.response.send_message("❌ Cannot find a game in the registration phase.", ephemeral=True)
        return

    players = get_registered_players_db(game.game_id)
    if len(players) < 2:
        await interaction.response.send_message(
            f"❌ You need at least 2 players to start! Currently have {len(players)}.", ephemeral=True)
        return

    # Now returns the full shuffled list of IDs
    ordered_players = start_game_db(game.game_id)
    if not ordered_players:
        await interaction.response.send_message(
            "❌ The game could not be started. It may have already been started.", ephemeral=True)
        return

    turn_order_text = _turn_order_lines(interaction.guild, ordered_players, unknown_name="Unknown Player")

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

    # Pin the message sent
    try:
        message = await interaction.original_response()
        await message.pin(reason="Listen Game Turn Order")
        update_game_start_message_db(game.game_id, message.id)
    except discord.Forbidden:
        logger.warning("Bot lacks permission to pin messages in the listen-game channel.")
    except discord.HTTPException as e:
        logger.error("Failed to pin the turn order message: %s", e)

@app_commands.command(name="listen-game-gm-sync-playlist",
                      description="[GM] Syncs DB submissions with the YouTube playlist.")
@app_commands.checks.has_role(Role.LISTEN_GAME_GM)
async def listen_game_gm_sync_playlist(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    ctx = await require_active_round(interaction, deferred=True)
    if not ctx:
        return

    playlist_id = ctx.round.playlist_id
    if not playlist_id:
        await interaction.followup.send("⚠️ No YouTube playlist has been generated for this round yet.")
        return

    submissions = get_round_submissions_db(ctx.round.round_id)
    if not submissions:
        await interaction.followup.send("ℹ️ There are no submissions in the database to sync.")
        return

    # Each of these is a blocking YouTube API call; the list call and the per-video
    # insert loop both run in a thread so they don't stall the event loop.
    try:
        existing_yt_vids = await asyncio.to_thread(get_playlist_video_ids, playlist_id)
    except QuotaExceededError:
        await interaction.followup.send(
            "❌ **YouTube API Quota Exceeded.** Nothing was changed. Please run this command again tomorrow.")
        return

    if existing_yt_vids is None:
        # Don't guess: treating an unreadable playlist as empty would re-add every song
        await interaction.followup.send(
            "❌ Couldn't read the YouTube playlist right now, so nothing was changed. Try again in a few minutes.")
        return

    missing_vids = [sub for sub in submissions if sub.video_id not in existing_yt_vids]

    if not missing_vids:
        await interaction.followup.send("✅ The YouTube playlist is completely up to date with the database!")
        return

    added_count, failed_count, quota_hit = await asyncio.to_thread(
        _sync_missing_videos, playlist_id, missing_vids
    )

    msg = f"🔄 **Sync Complete!**\nAdded {added_count} missing videos to the playlist."
    if failed_count > 0:
        msg += f"\n⚠️ Failed to add {failed_count} videos (they may be private or deleted)."

    if quota_hit:
        msg += "\n\n❌ **Sync halted: YouTube API Quota Exceeded.**\nPlease run this command again tomorrow."
        await interaction.followup.send(msg)

        await send_dm(
            interaction.client, get_active_gm_id(ctx.game, ctx.round),
            "🚨 **Listen Game Alert: YouTube API Quota Exceeded!**\n"
            "The bot ran out of YouTube API quota while trying to sync the playlist. "
            "No more songs can be added to the playlist today.\n\n"
            "Please run `/listen-game-gm-sync-playlist` tomorrow to finish syncing."
        )
        return

    await interaction.followup.send(msg)

def _sync_missing_videos(playlist_id: str, missing_vids: list[Submission]) -> tuple[int, int, bool]:
    """Synchronous worker: adds each missing video to the YouTube playlist."""
    added_count = 0
    failed_count = 0
    quota_hit = False

    for sub in missing_vids:
        try:
            success = add_video_to_playlist(playlist_id, sub.video_id)
            if success:
                added_count += 1
            else:
                failed_count += 1
        except QuotaExceededError:
            quota_hit = True
            break

    return added_count, failed_count, quota_hit

@app_commands.command(name="listen-game-gm-reject-song", description="[GM] Reject a player's submission.")
@app_commands.describe(
    player="The player whose song you are rejecting.",
    reason="The reason for rejection (sent to the player)."
)
@app_commands.checks.has_role(Role.LISTEN_GAME_GM)
async def listen_game_gm_reject_song(interaction: discord.Interaction, player: discord.Member, reason: str):
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    ctx = await require_active_round(
        interaction, deferred=True, statuses=(RoundStatus.SUBMITTING,),
        wrong_status_message="⚠️ Submissions are closed! You cannot reject a song at this phase.")
    if not ctx:
        return

    async with SUBMISSION_LOCK:
        submission = get_user_submission_db(ctx.round.round_id, player.id)
        if not submission:
            await interaction.followup.send(f"⚠️ {player.display_name} has not submitted a song for this round.")
            return

        delete_submission_db(ctx.round.round_id, player.id)

        # Delete from YouTube
        if ctx.round.playlist_id:
            yt_removed = await asyncio.to_thread(remove_video_from_playlist, ctx.round.playlist_id, submission.video_id)
            if not yt_removed:
                logger.warning("Failed to remove video %s from YT playlist during GM rejection.", submission.video_id)

    # DM the player
    dm_sent = await send_dm(
        interaction.client, player.id,
        f"🚨 **Listen Game Update** 🚨\n\n"
        f"The Game Master has rejected your submission for the current round (`{submission.raw_title}`).\n"
        f"**Reason:** {reason}\n\n"
        f"Please find a new track and use `/listen-game-submit-song` to try again!"
    )
    dm_status = "Player was DMed the reason." if dm_sent else \
        "Player has DMs disabled. You will need to ping them in the channel manually."

    # Acknowledge GM
    await interaction.followup.send(f"✅ **Success!** Removed `{submission.raw_title}`. {dm_status}")

@app_commands.command(name="listen-game-gm-skip-turn", description="[GM] Forcefully skip the current listener's turn.")
@app_commands.describe(
    player="The listener whose turn you are skipping.",
    reason="The reason for skipping (sent to the player)."
)
@app_commands.checks.has_role(Role.LISTEN_GAME_GM)
async def listen_game_gm_skip_turn(interaction: discord.Interaction, player: discord.Member, reason: str):
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    ctx = await require_active_round(interaction, deferred=True)
    if not ctx:
        return

    if ctx.round.host_id != player.id:
        current_host = interaction.guild.get_member(ctx.round.host_id)
        host_name = current_host.display_name if current_host else "Unknown"
        await interaction.followup.send(
            f"❌ {player.display_name} is not the current listener. The current listener is {host_name}.")
        return

    # Points are already saved once the reveal starts, so skipping now would leave it half-finished
    if ctx.round.status == RoundStatus.REVEALING:
        await interaction.followup.send(
            f"❌ {player.display_name}'s results are already being revealed. Let the reveal finish "
            "(the listener or GM can run `/listen-game-submit-ranking` to resume it if it stopped).")
        return

    # 1. Execute the skip
    next_host_id = skip_game_turn_db(ctx.game.game_id, ctx.round.round_id)

    # 2. DM the skipped player
    dm_sent = await send_dm(
        interaction.client, player.id,
        f"🚨 **Listen Game Update** 🚨\n\n"
        f"The Game Master has forcefully skipped your turn as listener for the current round.\n"
        f"**Reason:** {reason}\n\n"
        f"If you have questions, please reach out to the GM directly."
    )
    dm_status = "Player was DMed the reason." if dm_sent else \
        "Player has DMs disabled. You will need to ping them manually."

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

        leaderboard = get_game_leaderboard_db(ctx.game.game_id)
        if leaderboard:
            await listen_channel.send(generate_leaderboard_text(leaderboard))


@app_commands.command(name="listen-game-gm-remove-player", description="[GM] Remove a player from the game entirely.")
@app_commands.describe(
    player="The player to remove.",
    reason="The reason for removal (sent to the player)."
)
@app_commands.checks.has_role(Role.LISTEN_GAME_GM)
async def listen_game_gm_remove_player(interaction: discord.Interaction, player: discord.Member, reason: str):
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    # Check for a playing or registering game
    game = get_game_by_status_db(GameStatus.PLAYING) or get_game_by_status_db(GameStatus.REGISTRATION)
    if not game:
        await interaction.followup.send("⚠️ There is no active game right now.")
        return

    if player.id not in get_registered_players_db(game.game_id):
        await interaction.followup.send(f"⚠️ {player.display_name} is not in the current game.")
        return

    active_round = get_current_round_db(game.game_id) if game.status == GameStatus.PLAYING else None

    # Block removing the active host to prevent breaking the game state
    if active_round and active_round.host_id == player.id:
        await interaction.followup.send(
            f"❌ {player.display_name} is the current listener! Please use `/listen-game-gm-skip-turn` "
            "first to advance the game before removing them."
        )
        return

    remove_player_from_game_db(game.game_id, player.id)

    # While submissions are open, their song must go too: it would otherwise stay in the playlist and
    # count towards the round being complete
    submissions_open = active_round is not None and active_round.status == RoundStatus.SUBMITTING
    if submissions_open:
        async with SUBMISSION_LOCK:
            submission = get_user_submission_db(active_round.round_id, player.id)
            if submission and delete_submission_db(active_round.round_id, player.id) and active_round.playlist_id:
                await asyncio.to_thread(remove_video_from_playlist, active_round.playlist_id, submission.video_id)

    # Notify the player
    dm_sent = await send_dm(
        interaction.client, player.id,
        f"🚨 **Listen Game Update** 🚨\n\n"
        f"The Game Master has removed you from the current Listen Game.\n"
        f"**Reason:** {reason}\n\n"
        f"If you have questions, please reach out to the GM directly."
    )
    dm_status = "Player was DMed." if dm_sent else "Player has DMs disabled."

    # Acknowledge the GM and announce in channel
    await interaction.followup.send(f"✅ **Success!** {player.display_name} has been removed from the game. {dm_status}")
    await interaction.channel.send(f"The Game Master has removed {player.display_name} from the game.")

    # Check if removing this player caused the round to suddenly be complete!
    if submissions_open and is_round_complete_db(game.game_id, active_round.round_id):
        if close_round_db(active_round.round_id):
            await send_dm(
                interaction.client, active_round.host_id,
                "🎉 **All submissions are in for your Listen Game round!**\n\n"
                "A player was removed, which means everyone remaining has already submitted. "
                "The round has been automatically closed.\n\n"
                f"Here is your generated playlist to review: {playlist_link(active_round.playlist_id)}\n\n"
                "When you've decided your rankings, run `/listen-game-submit-ranking` in "
                "the channel to start the reveal!"
            )

@app_commands.command(name="listen-game-gm-force-start-round",
                      description="[GM] Force start ranking phase by explicitly skipping outstanding players.")
@app_commands.describe(skipped_users="Tag the exact users you are skipping (e.g., @User1 @User2).")
@app_commands.checks.has_role(Role.LISTEN_GAME_GM)
async def listen_game_gm_force_start_round(interaction: discord.Interaction, skipped_users: str):
    """
    Forcefully advances a round to the ranking phase.

    This command requires the GM to explicitly mention all players who have not yet
    submitted. If the mentions do not match the database state, the command fails.
    """
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    ctx = await require_active_round(
        interaction, deferred=True, statuses=(RoundStatus.SUBMITTING,),
        wrong_status_message="⚠️ The round is not currently in the submission phase.")
    if not ctx:
        return

    # Identify missing players
    all_players = get_registered_players_db(ctx.game.game_id)
    submitted_ids = {sub.user_id for sub in get_round_submissions_db(ctx.round.round_id)}
    host_id = ctx.round.host_id
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
    if not close_round_db(ctx.round.round_id):
        await interaction.followup.send(ROUND_ALREADY_MOVED_ON)
        return

    await update_submission_tracker(
        interaction.channel, ctx,
        extra_text=f"\n⏭️ **Round forced closed by GM!** Playlist sent to <@{host_id}>!")

    # Notify the Host
    host_notified = await send_dm(
        interaction.client, host_id,
        "🚨 **Round Force-Closed!**\n\n"
        "The GM has manually ended the submission phase, skipping the remaining players.\n\n"
        f"Playlist: {playlist_link(ctx.round.playlist_id)}\n\n"
        "Run `/listen-game-submit-ranking` in the channel to start the reveal!"
    )
    dm_status = "Listener notified via DM." if host_notified else "Listener has DMs disabled."

    await interaction.followup.send(f"✅ **Success!** Round forced closed. {dm_status}")

@app_commands.command(name="listen-game-gm-force-submit",
                      description="[GM] Bypass filters to forcefully submit a song for a player.")
@app_commands.describe(
    player="The player you are submitting for.",
    url="The YouTube link to the song."
)
@app_commands.checks.has_role(Role.LISTEN_GAME_GM)
async def listen_game_gm_force_submit(interaction: discord.Interaction, player: discord.Member, url: str):
    """
    Forcefully adds a submission for a player, bypassing fuzzy match blocks.
    Updates the live tracker and handles round completion just like a normal submission.
    """
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    async with SUBMISSION_LOCK:
        await _process_forced_submission(interaction, player, url)


async def _process_forced_submission(interaction: discord.Interaction, player: discord.Member, url: str):
    ctx = await require_active_round(
        interaction, deferred=True, statuses=(RoundStatus.SUBMITTING,),
        wrong_status_message="⚠️ The round is not currently in the submission phase.")
    if not ctx:
        return
    active_round = ctx.round

    if player.id == active_round.host_id:
        await interaction.followup.send("❌ You cannot submit a song for the current listener.")
        return

    # Extract data
    video_id = extract_video_id(url)
    if not video_id:
        await interaction.followup.send("❌ Invalid YouTube URL.")
        return

    video_title = await asyncio.to_thread(get_video_title, video_id)
    if not video_title:
        await interaction.followup.send("❌ Could not fetch that video. It may be private or deleted.")
        return

    # Handle YouTube Playlist Swap & Addition. A first-time submission has no previous song to
    # remove, and the playlist is created if this is the round's first song.
    previous_submission = get_user_submission_db(active_round.round_id, player.id)
    outcome, playlist_id = await asyncio.to_thread(
        put_song_in_round_playlist,
        get_host_name(interaction.guild, active_round.host_id), active_round, video_id,
        previous_submission.video_id if previous_submission else None
    )

    if outcome is PlaylistOutcome.CREATE_FAILED:
        await interaction.followup.send("❌ Could not create the YouTube playlist for this round. Check the logs.")
        return

    if outcome is PlaylistOutcome.ADD_FAILED:
        await interaction.followup.send("❌ Failed to add video to the playlist. It may be blocked or private.")
        return

    upsert_submission_db(active_round.round_id, player.id, video_id, video_title)
    player_dm = f"✅ The GM has forcefully submitted your song `{video_title}` for the Listen Game!"

    if outcome is PlaylistOutcome.QUOTA_EXCEEDED:
        # Handle YouTube Quota limits gracefully: the song is saved and can be synced later
        await interaction.followup.send(
            f"✅ **Success!** `{video_title}` accepted into the database for {player.display_name}.\n\n"
            "⚠️ *Note: YouTube API limits have been reached. "
            "Run `/listen-game-gm-sync-playlist` tomorrow to push it to the playlist.*"
        )
        await send_dm(interaction.client, player.id, player_dm)
        return

    await update_submission_tracker(interaction.channel, ctx)

    # Final Completion Check & DM to Host
    if not previous_submission and is_round_complete_db(ctx.game.game_id, active_round.round_id):
        if close_round_db(active_round.round_id):
            await send_dm(
                interaction.client, active_round.host_id,
                "🎉 **All submissions are in for your Listen Game round!**\n\n"
                "The round has been automatically closed. Here is your generated playlist to review: "
                f"{playlist_link(playlist_id)}\n\nWhen you've decided your rankings, run "
                "`/listen-game-submit-ranking` in the channel to start the reveal!"
            )

    # Notify Player & Respond to GM
    player_notified = await send_dm(interaction.client, player.id, player_dm)
    dm_status = "Player was DMed." if player_notified else "Player has DMs disabled."

    if previous_submission:
        await interaction.followup.send(
            f"🔄 **Updated!** Swapped submission to `{video_title}` for {player.display_name}. {dm_status}")
    else:
        await interaction.followup.send(
            f"✅ **Success!** `{video_title}` accepted for {player.display_name}. {dm_status}")

@app_commands.command(name="listen-game-gm-approve-playlist",
                      description="[GM] Approve the round's playlist and notify the listener.")
@app_commands.checks.has_role(Role.LISTEN_GAME_GM)
async def listen_game_gm_approve_playlist(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    # Use ephemeral so the GM's command usage doesn't clutter the chat
    await interaction.response.defer(ephemeral=True)

    ctx = await require_active_round(
        interaction, deferred=True, statuses=(RoundStatus.SUBMITTING,),
        wrong_status_message="⚠️ The round is not in the submission phase.")
    if not ctx:
        return

    if not is_round_complete_db(ctx.game.game_id, ctx.round.round_id):
        await interaction.followup.send("⚠️ Cannot approve yet! Not all players have submitted a song.")
        return

    # Close the round in the database (transitions state to 'ranking')
    if not close_round_db(ctx.round.round_id):
        await interaction.followup.send(ROUND_ALREADY_MOVED_ON)
        return

    host_member = interaction.guild.get_member(ctx.round.host_id)
    host_mention = host_member.mention if host_member else "the listener"

    await update_submission_tracker(interaction.channel, ctx)

    # DM the Host that they can begin ranking
    host_notified = await send_dm(
        interaction.client, ctx.round.host_id,
        "🎉 **All submissions are in for your Listen Game ruleset!**\n\n"
        f"Here is your playlist to review: {playlist_link(ctx.round.playlist_id)}\n\n"
        "When you've decided your rankings, use `/listen-game-submit-ranking` in #listen-game!"
    )
    dm_status = "Listener notified via DM." if host_notified else "Listener has DMs disabled."

    # Announce it publicly in the channel
    try:
        await interaction.channel.send(
            f"✅ **Playlist Approved!**\n"
            f"{host_mention}, all submissions are in and your playlist has been sent to your DMs! "
            "Please review the songs and use `/listen-game-submit-ranking` when you are ready."
        )
    except discord.Forbidden:
        logger.warning("Failed to send public approval message. Check bot permissions in #listen-game.")

    # Acknowledge the GM
    await interaction.followup.send(
        f"✅ **Success!** The round has been closed and the playlist sent to {host_mention}. {dm_status}")

@app_commands.command(name="listen-game-gm-swap-players",
                      description="[GM] Swap the turn order of two players who have yet to be the listener.")
@app_commands.describe(
    player1="The first player to swap.",
    player2="The second player to swap."
)
@app_commands.checks.has_role(Role.LISTEN_GAME_GM)
async def listen_game_gm_swap_players(
    interaction: discord.Interaction,
    player1: discord.Member,
    player2: discord.Member
):
    game = get_game_by_status_db(GameStatus.PLAYING)
    if not game:
        await interaction.response.send_message("⚠️ There is no active Listen Game currently running.",
                                                ephemeral=True)
        return

    if player1.id == player2.id:
        await interaction.response.send_message("❌ You cannot swap a player with themselves.", ephemeral=True)
        return

    outcome = swap_player_orders_db(game.game_id, player1.id, player2.id)
    if outcome is not SwapOutcome.SWAPPED:
        await interaction.response.send_message(_SWAP_FAILURES[outcome], ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    # Build the new turn order text
    ordered_players = get_ordered_players_db(game.game_id)
    turn_order_text = _turn_order_lines(interaction.guild, ordered_players)

    # Directly fetch the message by ID and update it
    if game.game_start_message_id:
        try:
            start_msg = await interaction.channel.fetch_message(game.game_start_message_id)
            if start_msg.embeds:
                embed = start_msg.embeds[0]
                # Overwrite the description with the new turn order
                embed.description = (
                    f"Registration is closed and the turn order has been randomized!\n\n"
                    f"**Turn Order:**\n{turn_order_text}\n\n"
                    f"Our first listener is <@{ordered_players[0]}>! "
                    "Please use `/listen-game-post-ruleset` when you are ready to post your rules for Round 1."
                )
                await start_msg.edit(embed=embed)
        except discord.NotFound:
            logger.warning("Game start message %s not found.", game.game_start_message_id)
        except discord.HTTPException as e:
            logger.error("Failed to update the turn order message: %s", e)

    # Send the success confirmation to the channel
    await interaction.followup.send(
        f"🔄 {player1.mention} and {player2.mention} have swapped positions in the turn order. "
        "The pinned turn order message has been updated!"
    )
