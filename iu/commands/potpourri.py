"""Commands for Potpourri"""
import csv
import io
import logging
import discord
from discord import app_commands
from services.youtube import (
    create_playlist,
    add_video_to_playlist,
    extract_video_id,
    QuotaExceededError
)

logger = logging.getLogger('iu-bot')

@app_commands.command(name='create-potpourri-playlist',
                      description="[Admin] Upload a CSV to generate the potpourri YouTube playlist.")
@app_commands.describe(
    file="The .csv file containing Discord Names and Video Links",
    playlist_title="The title for the new YouTube playlist"
)
@app_commands.default_permissions(administrator=True)
async def create_potpourri_playlist(interaction: discord.Interaction, file: discord.Attachment, playlist_title: str):
    # This might take a while depending on the number of videos, so we defer
    await interaction.response.defer(ephemeral=True)

    if not file.filename.endswith('.csv'):
        await interaction.followup.send("❌ Please upload a valid `.csv` file.")
        return

    try:
        # Read the file directly from Discord's CDN into memory
        csv_bytes = await file.read()
        csv_text = csv_bytes.decode('utf-8-sig') # utf-8-sig handles potential BOM characters from Excel
        reader = csv.DictReader(io.StringIO(csv_text))
        # Dynamically find the right columns just in case the form question changes slightly
        name_col = next((col for col in reader.fieldnames if 'name' in col.lower() or 'discord' in col.lower()), None)
        link_col = next((col for col in reader.fieldnames if 'link' in col.lower() or 'url' in col.lower()), None)

        if not name_col or not link_col:
            await interaction.followup.send("❌ Could not identify the 'Name' or 'Link' columns in the CSV.")
            return

        # Group links by user
        user_links = {}
        for row in reader:
            user = row.get(name_col)
            link = row.get(link_col)

            if user and link:
                user = user.strip()
                video_id = extract_video_id(link)
                if video_id:
                    if user not in user_links:
                        user_links[user] = []
                    user_links[user].append(video_id)

        if not user_links:
            await interaction.followup.send("❌ No valid YouTube links were found in the uploaded file.")
            return

        # Round-Robin Sorting Algorithm
        ordered_videos = []
        active_users = list(user_links.keys())

        while active_users:
            for user in list(active_users):
                if user_links[user]:
                    ordered_videos.append(user_links[user].pop(0))
                # Remove the user from the rotation if they have no more links
                if not user_links[user]:
                    active_users.remove(user)

        # Create the Playlist
        playlist_id = create_playlist(playlist_title, "K-Potpourri Playlist")
        if not playlist_id:
            await interaction.followup.send(
                "❌ Failed to create the YouTube playlist. Check your API Quota and bot logs.")
            return

        # Populate the Playlist
        added_count = 0
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        for vid in ordered_videos:
            try:
                success = add_video_to_playlist(playlist_id, vid)
                if success:
                    added_count += 1
            except QuotaExceededError:
                await interaction.followup.send(
                    f"⚠️ **Quota Exceeded mid-process!**\n"
                    f"Added {added_count} out of {len(ordered_videos)} videos before hitting the YouTube API limit.\n"
                    f"🔗 {url}"
                )
                return

        await interaction.followup.send(
            f"✅ **K-Potpourri Playlist Created!**\n"
            f"Successfully organized and added **{added_count}/{len(ordered_videos)}** videos in round-robin order.\n\n"
            f"🔗 {url}"
        )

    except Exception as e:
        logger.error("Error processing watch party CSV: %s", e)
        await interaction.followup.send(f"❌ An error occurred while processing the file: {e}")
