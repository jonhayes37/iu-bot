"""Commands for the listen game"""
import asyncio

import discord
from discord import app_commands
from config import Channel, Role
from db.listen_game import (
    RoundStatus, get_active_gm_id, get_ranking_picks_db, get_round_submissions_db, get_user_submission_db,
    is_round_complete_db, is_video_claimed_by_other_db, upsert_submission_db
)
from services.listen_game import RoundContext, playlist_link, require_active_round, send_dm, update_submission_tracker
from services.listen_game_playlist import (
    SUBMISSION_LOCK, PlaylistOutcome, get_host_name, put_song_in_round_playlist
)
from services.listen_game_reveal import start_reveal
from services.youtube import get_video_title, extract_video_id
from ui.listen_game import SetThemeModal, ListenGameRankingView
from utils.validation import validate_channel


@app_commands.command(name="listen-game-post-ruleset",
                      description="[Listener] Set or update the ruleset for your round.")
@app_commands.checks.has_role(Role.LISTEN_GAME_PLAYER)
async def listen_game_set_theme(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    ctx = await require_active_round(interaction, deferred=False)
    if not ctx:
        return
    active_round = ctx.round

    if interaction.user.id != active_round.host_id:
        host = interaction.guild.get_member(active_round.host_id)
        host_name = host.mention if host else "the current listener"
        await interaction.response.send_message(
            f"❌ You are not the listener for this round! We are waiting on {host_name}.", ephemeral=True)
        return

    # Check if a ruleset already exists
    if active_round.theme:
        round_is_full = is_round_complete_db(ctx.game.game_id, active_round.round_id)
        if active_round.status != RoundStatus.SUBMITTING or round_is_full:
            await interaction.response.send_message(
                "❌ All players have already submitted their songs! You can no longer change the ruleset.",
                ephemeral=True
            )
            return
    elif active_round.status != RoundStatus.SETTING_THEME:
        await interaction.response.send_message(
            "⚠️ The game is not currently waiting for a ruleset.", ephemeral=True)
        return

    # Launch the modal, passing in the existing data (if any)
    modal = SetThemeModal(
        game_id=ctx.game.game_id,
        round_id=active_round.round_id,
        existing_theme=active_round.theme,
        ruleset_msg_id=active_round.ruleset_message_id
    )
    await interaction.response.send_modal(modal)


@app_commands.command(name="listen-game-submit-song",
                      description="Submit or update your YouTube track for the current round.")
@app_commands.describe(url="The YouTube link to your song.")
@app_commands.checks.has_role(Role.LISTEN_GAME_PLAYER)
async def submit_song(interaction: discord.Interaction, url: str):
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    await interaction.response.defer(ephemeral=True)

    # One submission at a time: the "already claimed" check, the playlist update and the save must
    # not interleave between two players
    async with SUBMISSION_LOCK:
        await _process_submission(interaction, url)


async def _process_submission(interaction: discord.Interaction, url: str):
    ctx = await require_active_round(
        interaction, deferred=True, statuses=(RoundStatus.SUBMITTING,),
        wrong_status_message="⚠️ The round is not currently accepting submissions.")
    if not ctx:
        return
    active_round = ctx.round
    user = interaction.user

    if user.id == active_round.host_id:
        await interaction.followup.send("❌ You are the listener! You don't submit a song for your own round.")
        return

    video_id = extract_video_id(url)
    if not video_id:
        await interaction.followup.send("❌ Invalid YouTube URL.")
        return

    video_title = await asyncio.to_thread(get_video_title, video_id)
    if not video_title:
        await interaction.followup.send("❌ Could not fetch that video. It may be private or deleted.")
        return

    if is_video_claimed_by_other_db(active_round.round_id, user.id, video_id):
        await interaction.followup.send(
            "❌ **Song Already Claimed!** Someone else has already submitted this exact video for this round."
        )
        return

    previous_submission = get_user_submission_db(active_round.round_id, user.id)
    if previous_submission and previous_submission.video_id == video_id:
        await interaction.followup.send("⚠️ You have already submitted this exact video!")
        return

    outcome, playlist_id = await asyncio.to_thread(
        put_song_in_round_playlist,
        get_host_name(interaction.guild, active_round.host_id), active_round, video_id,
        previous_submission.video_id if previous_submission else None
    )

    if outcome is PlaylistOutcome.CREATE_FAILED:
        await interaction.followup.send("❌ Internal Error: Could not create YouTube playlist. Contact the GM.")
        return

    if outcome is PlaylistOutcome.ADD_FAILED:
        await interaction.followup.send("❌ Failed to add video to the playlist. It may be blocked or private.")
        return

    upsert_submission_db(active_round.round_id, user.id, video_id, video_title)

    if outcome is PlaylistOutcome.QUOTA_EXCEEDED:
        # The song is saved anyway; the GM catches the playlist up later
        await interaction.followup.send(
            f"✅ **Success!** Your song `{video_title}` has been accepted into the database.\n\n"
            "⚠️ *Note: YouTube API limits have been reached for today, so it is not in the "
            "playlist yet. The GM has been notified to sync it tomorrow.*"
        )
        await send_dm(
            interaction.client, get_active_gm_id(ctx.game, active_round),
            "🚨 **Listen Game Alert: YouTube Quota Exceeded!**\n"
            "A player submitted a song, but the bot could not add it to the playlist due to "
            "YouTube API limits. The song is safely stored in the database.\n\n"
            "**Please run `/listen-game-gm-sync-playlist` tomorrow** when the quota "
            "resets to catch the playlist up!"
        )
        return

    if previous_submission:
        await interaction.followup.send(f"🔄 **Updated!** Your submission has been swapped to `{video_title}`.")
    else:
        await interaction.followup.send(f"✅ **Success!** Your song `{video_title}` has been accepted.")

    await send_dm(
        interaction.client, get_active_gm_id(ctx.game, active_round),
        f"🎵 **New Listen Game Submission!**\n\n"
        f"**Player:** {user.display_name}\n"
        f"**Song:** `{video_title}`\n"
        f"**URL:** {url}\n\n"
        "You can review this round's playlist or use `/listen-game-gm-reject-song` if this is a duplicate."
    )

    await update_submission_tracker(interaction.channel, ctx)

    # When the last song comes in, route to the GM instead of closing the round
    if not previous_submission and is_round_complete_db(ctx.game.game_id, active_round.round_id):
        await _notify_gm_all_submitted(interaction, ctx, playlist_id)


async def _notify_gm_all_submitted(interaction: discord.Interaction, ctx: RoundContext, playlist_id: str | None):
    """DMs the GM the ledger of everything submitted so they can review it and approve the round."""
    summary_lines = []
    for submission in get_round_submissions_db(ctx.round.round_id):
        member = interaction.guild.get_member(submission.user_id)
        name = member.display_name if member else f"User ID {submission.user_id}"
        summary_lines.append(f"• **{name}**: `{submission.raw_title}`")

    await send_dm(
        interaction.client, get_active_gm_id(ctx.game, ctx.round),
        "**Listen Game: All Submissions Are In!**\n\n"
        f"Here is the playlist: {playlist_link(playlist_id)}\n\n"
        "**Submission Ledger (For Review):**\n"
        + "\n".join(summary_lines) + "\n\n"
        "Please review the submissions for duplicates. "
        "If you need to reject a song, use "
        "`/listen-game-gm-reject-song @player [reason]`.\n"
        "If everything looks good, run `/listen-game-gm-approve-playlist` "
        f"in {interaction.channel.mention} to publish it to the channel and notify the listener!"
    )


@app_commands.command(name="listen-game-submit-ranking",
                      description="[Listener] Rank the submissions and provide commentary.")
@app_commands.checks.has_role(Role.LISTEN_GAME_PLAYER)
async def listen_game_submit_ranking(interaction: discord.Interaction):
    restricted = await validate_channel(interaction, Channel.LISTEN_GAME)
    if restricted:
        return

    ctx = await require_active_round(interaction, deferred=False)
    if not ctx:
        return
    active_round = ctx.round

    # Results are already saved; this is a reveal that was interrupted (e.g. by a restart), so resume it
    if active_round.status == RoundStatus.REVEALING:
        if interaction.user.id not in (active_round.host_id, get_active_gm_id(ctx.game, active_round)):
            await interaction.response.send_message(
                "❌ Only the listener or the GM can resume the reveal.", ephemeral=True)
            return

        if start_reveal(interaction.channel, active_round.round_id):
            message = "▶️ Resuming the reveal in this channel."
        else:
            message = "⏳ The reveal is already in progress."
        await interaction.response.send_message(message, ephemeral=True)
        return

    # Ensure the round has actually been closed/timed out
    if active_round.status != RoundStatus.RANKING:
        await interaction.response.send_message(
            "⚠️ Submissions are still open! Wait for the deadline or ask the GM to close the round.", ephemeral=True)
        return

    if interaction.user.id != active_round.host_id:
        await interaction.response.send_message(
            "❌ Only the listener of the current round can submit the rankings.", ephemeral=True)
        return

    # Fetch all submissions to populate the dropdown
    submissions = get_round_submissions_db(active_round.round_id)
    if not submissions:
        await interaction.response.send_message("❌ No submissions found for this round.", ephemeral=True)
        return

    # Anything the listener had already ranked before a restart or a dismissed message is picked back up
    view = ListenGameRankingView(submissions, get_ranking_picks_db(active_round.round_id),
                                 ctx.game.game_id, active_round.round_id, interaction.channel.id)
    await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)
