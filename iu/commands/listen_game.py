"""Commands for the listen game"""
import logging
import typing

import discord
from discord import app_commands
from db.listen_game import (
    create_game_db, get_current_round_db, get_game_by_status_db,
    get_registered_players_db, get_round_submissions_db, start_game_db,
    update_round_playlist_db, is_round_complete_db, upsert_submission_db,
    get_user_submission_db
)
from services.youtube import (
    get_video_title, create_listen_game_playlist, add_video_to_playlist,
    remove_video_from_playlist, extract_video_id, QuotaExceededError
)
from ui.listen_game import JoinGameView, SetThemeModal, ListenGameRankingView
from utils.validation import validate_channel

logger = logging.getLogger('iu-bot')


@app_commands.command(name="listen-game-create", description="[GM] Open a new Listen Game for registration.")
@app_commands.describe(max_round_days="Optional: Auto-close rounds after X days if players haven't submitted.")
@app_commands.default_permissions(administrator=True)
async def listen_game_create(interaction: discord.Interaction, max_round_days: typing.Optional[int] = None):
    restricted = await validate_channel(interaction, 'sandbox')
    if restricted:
        return

    game_id = create_game_db(interaction.user.id, max_round_days)
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
@app_commands.default_permissions(administrator=True)
async def listen_game_start(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, 'sandbox')
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
            f"Our first host is <@{ordered_players[0]}>! "
            "Please use `/listen-game-post-theme` when you are ready to post your rules for Round 1."
        ),
        color=0x2ecc71
    )

    await interaction.response.send_message(content=f"<@{ordered_players[0]}>", embed=embed)


@app_commands.command(name="listen-game-post-theme", description="[Host] Set the theme and rules for your round.")
async def listen_game_set_theme(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, 'sandbox')
    if restricted:
        return

    # Check if a game is actually playing
    game = get_game_by_status_db('playing')
    if not game:
        await interaction.response.send_message("⚠️ There is no active game right now.", ephemeral=True)
        return

    # Fetch the current round
    active_round = get_current_round_db(game['game_id'])
    if not active_round:
        await interaction.response.send_message("⚠️ Could not find an active round.", ephemeral=True)
        return

    # Check the phase
    if active_round['status'] != 'setting_theme':
        await interaction.response.send_message("⚠️ The game is not currently waiting for a theme.", ephemeral=True)
        return

    # Authenticate the host
    if interaction.user.id != active_round['host_id']:
        host = interaction.guild.get_member(active_round['host_id'])
        host_name = host.mention if host else "the current host"
        await interaction.response.send_message(
            f"❌ You are not the host for this round! We are waiting on {host_name}.", ephemeral=True)
        return

    # Launch the Modal
    await interaction.response.send_modal(SetThemeModal(game['game_id'], active_round['round_id']))


@app_commands.command(name="listen-game-submit-song",
                      description="Submit or update your YouTube track for the current round.")
@app_commands.describe(url="The YouTube link to your song.")
async def submit_song(interaction: discord.Interaction, url: str):
    restricted = await validate_channel(interaction, 'sandbox')
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    game = get_game_by_status_db('playing')
    if not game:
        await interaction.followup.send("⚠️ There is no active game right now.")
        return

    active_round = get_current_round_db(game['game_id'])
    if not active_round or active_round['status'] != 'submitting':
        await interaction.followup.send("⚠️ The round is not currently accepting submissions.")
        return

    if interaction.user.id == active_round['host_id']:
        await interaction.followup.send("❌ You are the host! You don't submit a song for your own round.")
        return

    # Extract Data
    video_id = extract_video_id(url)
    if not video_id:
        await interaction.followup.send("❌ Invalid YouTube URL.")
        return

    video_title = get_video_title(video_id)
    if not video_title:
        await interaction.followup.send("❌ Could not fetch that video. It may be private or deleted.")
        return

    # Handle Previous Submissions & Duplicate Checking
    user_previous_sub = get_user_submission_db(active_round['round_id'], interaction.user.id)
    if user_previous_sub and user_previous_sub['video_id'] == video_id:
        await interaction.followup.send("⚠️ You have already submitted this exact video!")
        return

    # Handle the YouTube Playlist Swap
    playlist_id = active_round['playlist_id']
    try:
        if playlist_id and user_previous_sub:
            removed = remove_video_from_playlist(playlist_id, user_previous_sub['video_id'])
            if not removed:
                logger.warning("Failed to remove old video %s during swap.", user_previous_sub['video_id'])

        if not playlist_id:
            host_member = interaction.guild.get_member(active_round['host_id'])
            host_name = host_member.display_name if host_member else "Unknown"
            playlist_id = create_listen_game_playlist(host_name)
            if playlist_id:
                update_round_playlist_db(active_round['round_id'], playlist_id)
                active_round['playlist_id'] = playlist_id
            else:
                await interaction.followup.send("❌ Internal Error: Could not create YouTube playlist. Contact the GM.")
                return

        added = add_video_to_playlist(playlist_id, video_id)
        if not added:
            await interaction.followup.send("❌ Failed to add video to the playlist. It may be blocked or private.")
            return

    except QuotaExceededError:
        # Save to DB anyway, but notify the GM
        upsert_submission_db(active_round['round_id'], interaction.user.id, video_id, video_title)

        await interaction.followup.send(
            f"✅ **Success!** Your song `{video_title}` has been accepted into the database.\n\n"
            "⚠️ *Note: YouTube API limits have been reached for today, so it is not in the "
            "playlist yet. The GM has been notified to sync it tomorrow.*"
        )

        gm_user = interaction.client.get_user(game['gm_id']) or await interaction.client.fetch_user(game['gm_id'])
        if gm_user:
            try:
                await gm_user.send(
                    "🚨 **Listen Game Alert: YouTube Quota Exceeded!**\n"
                    "A player submitted a song, but the bot could not add it to the playlist due to "
                    "YouTube API limits. The song is safely stored in the database.\n\n"
                    "**Please run `/listen-game-gm-sync-playlist` tomorrow** when the quota "
                    "resets to catch the playlist up!"
                )
            except discord.Forbidden:
                logger.warning("Could not DM GM about quota limits.")
        return

    # Save and Announce (Happy Path)
    upsert_submission_db(active_round['round_id'], interaction.user.id, video_id, video_title)
    if user_previous_sub:
        await interaction.followup.send(f"🔄 **Updated!** Your submission has been swapped to `{video_title}`.")
    else:
        await interaction.followup.send(f"✅ **Success!** Your song `{video_title}` has been accepted.")

    # Update the tracker message
    all_players = get_registered_players_db(game['game_id'])
    total_needed = len(all_players) - 1
    current_submissions = get_round_submissions_db(active_round['round_id'])
    current_count = len(current_submissions)
    is_complete = is_round_complete_db(game['game_id'], active_round['round_id'])
    if active_round.get('status_message_id'):
        try:
            tracker_msg = await interaction.channel.fetch_message(active_round['status_message_id'])
            tracker_text = f"🎧 **Round Status:** We are at `{current_count}/{total_needed}` submissions for the round."

            if is_complete:
                tracker_text += "\n\n✅ **All submissions received! Awaiting GM approval.**"

            await tracker_msg.edit(content=tracker_text)
        except Exception as e:
            logger.warning("Failed to update status message: %s", e)

    # Completion Check - Route to GM instead of closing the round
    if not user_previous_sub and is_complete:
        gm_user = interaction.client.get_user(game['gm_id']) or await interaction.client.fetch_user(game['gm_id'])
        if gm_user:
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            try:
                await gm_user.send(
                    "**Listen Game: All Submissions Are In!**\n\n"
                    f"Here is the playlist: {playlist_url}\n\n"
                    "Please review the submissions for duplicates. If everything looks good, "
                    "run `/listen-game-gm-approve-playlist` "
                    "in #listen-game to publish it to the channel and notify the host!"
                )
            except discord.Forbidden:
                logger.warning("Could not DM GM about round completion.")


@app_commands.command(name="listen-game-submit-ranking",
                      description="[Host] Rank the submissions and provide commentary.")
async def listen_game_submit_ranking(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, 'sandbox')
    if restricted:
        return

    game = get_game_by_status_db('playing')
    if not game:
        await interaction.response.send_message("⚠️ There is no active game right now.", ephemeral=True)
        return

    active_round = get_current_round_db(game['game_id'])
    if not active_round:
        await interaction.response.send_message("⚠️ Could not find an active round.", ephemeral=True)
        return

    # Ensure the round has actually been closed/timed out
    if active_round['status'] != 'ranking':
        await interaction.response.send_message(
            "⚠️ Submissions are still open! Wait for the deadline or ask the GM to close the round.", ephemeral=True)
        return

    if interaction.user.id != active_round['host_id']:
        await interaction.response.send_message(
            "❌ Only the host of the current round can submit the rankings.", ephemeral=True)
        return

    # Fetch all submissions to populate the dropdown
    submissions = get_round_submissions_db(active_round['round_id'])
    if not submissions:
        await interaction.response.send_message("❌ No submissions found for this round.", ephemeral=True)
        return

    view = ListenGameRankingView(submissions, game['game_id'], active_round['round_id'], interaction.channel.id)
    embed = discord.Embed(
        title="Listen Game Rankings",
        description="Select your #1 pick from the dropdown below. "
            "You will be prompted to enter your commentary for each song.",
        color=0x3498db
    )

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
