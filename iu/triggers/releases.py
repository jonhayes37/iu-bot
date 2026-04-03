"""
Handles parsing messages for YouTube links and storing them in the database.
"""

import re
import logging
from datetime import datetime
import discord
from db.releases import add_new_release, get_playlist_id_for_year, save_new_playlist, mark_release_processed
from services.youtube import create_playlist, add_video_to_playlist, get_video_publish_date, extract_video_id

logger = logging.getLogger('iu-bot')


async def store_new_release(message: discord.Message):
    """Parses a message, stores the release, and automatically syncs it to YouTube."""
    raw_urls = re.findall(r'(https?://[^\s]+)', message.content)
    if not raw_urls:
        return

    videos_processed = 0
    award_year = get_eligible_year(message.created_at)
    for url in raw_urls:
        video_id = extract_video_id(url)
        if not video_id:
            continue

        try:
            # Check the video publish date to ensure it's eligible for the current award year
            publish_date = get_video_publish_date(video_id)
            if not publish_date:
                logger.warning("Could not fetch publish date for %s. Skipping.", video_id)
                continue

            # If the video isn't from the current year, ignore it
            video_award_year = get_eligible_year(publish_date)
            if video_award_year != award_year:
                logger.info("Skipped %s: Video year (%s) does not match active year (%s).",
                            video_id, video_award_year, award_year)
                continue

            # Save to database initially as unprocessed (processed=0)
            added = add_new_release(video_id=video_id,
                                    original_url=url,
                                    message_id=str(message.id),
                                    msg_time=message.created_at)

            if added:
                # Check for existing playlist for this specific year
                playlist_id = get_playlist_id_for_year(award_year)

                # Create the playlist if it doesn't exist
                if not playlist_id:
                    logger.info("Playlist for %s not found. Creating...", award_year)
                    playlist_id = create_playlist(award_year)
                    if playlist_id:
                        save_new_playlist(award_year, playlist_id)

                # Add video and mark as processed
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
