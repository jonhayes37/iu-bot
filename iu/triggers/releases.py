"""
Handles parsing messages for YouTube links and storing them in the database.
"""

import re
import logging
from datetime import datetime
import discord
from db.releases import add_new_release, get_playlist_id_for_year, save_new_playlist, mark_release_processed
from services.youtube import create_playlist, add_video_to_playlist

logger = logging.getLogger('iu-bot')

# Robust RegEx that catches standard, mobile, embedded, and shortened YouTube URLs
YT_REGEX = re.compile(
    r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|'
    r'(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
)

async def store_new_release(message: discord.Message):
    """Parses a message, stores the release, and automatically syncs it to YouTube."""
    raw_urls = re.findall(r'(https?://[^\s]+)', message.content)
    if not raw_urls:
        return

    videos_processed = 0
    award_year = get_eligible_year(message.created_at)
    for url in raw_urls:
        match = YT_REGEX.search(url)
        if not match:
            continue

        video_id = match.group(1)

        try:
            # 1. Save to database initially as unprocessed (processed=0)
            added = add_new_release(video_id=video_id,
                                    original_url=url,
                                    message_id=str(message.id),
                                    msg_time=message.created_at)

            if added:
                # 2. Check for existing playlist for this specific year
                playlist_id = get_playlist_id_for_year(award_year)

                # 3. Create the playlist if it doesn't exist
                if not playlist_id:
                    logger.info("Playlist for %s not found. Creating...", award_year)
                    playlist_id = create_playlist(award_year)
                    if playlist_id:
                        save_new_playlist(award_year, playlist_id)

                # 4. Add video and mark as processed
                if playlist_id:
                    success = add_video_to_playlist(playlist_id, video_id)
                    if success:
                        mark_release_processed(video_id)
                        videos_processed += 1

        except Exception as ex:
            logger.error("Failed to process release %s: %s", video_id, ex)

    if videos_processed > 0:
        await message.add_reaction('<:iu:802970899174129744>')

def get_eligible_year(timestamp: datetime) -> int:
    """Calculates the award year (Dec 1st starts the next year)."""
    if timestamp.month == 12:
        return timestamp.year + 1
    return timestamp.year
