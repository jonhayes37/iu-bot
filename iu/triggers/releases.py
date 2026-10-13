"""
Handles parsing messages for YouTube links and storing them in the database.
"""

import asyncio
import re
import logging
from datetime import datetime
import discord
from config import EMOJI_IU
from db.releases import AddResult, add_new_release, get_playlist_id_for_year, save_new_playlist, mark_release_processed
from services.youtube import (
    QuotaExceededError, add_video_to_playlist, create_releases_playlist, extract_video_id, get_video_snippets,
    parse_publish_date
)
from utils.end_of_year import award_year_for

logger = logging.getLogger('iu-bot')

# The YouTube work runs in worker threads, so two messages could otherwise be processed at once. One
# release is handled at a time so that a video posted twice in quick succession sees the first post's
# finished state (and is a duplicate) instead of being added to the playlist again, and so the year's
# playlist can't be created twice.
RELEASE_LOCK = asyncio.Lock()


async def store_new_release(message: discord.Message):
    """Parses a message, stores the release, and automatically syncs it to YouTube."""
    await store_new_releases([message])

async def store_new_releases(messages: list[discord.Message]):
    """
    Handles the YouTube links in several messages at once. Their videos are looked up together
    (up to 50 per YouTube request), which matters for a backfill over many messages.
    """
    links = []  # (message, url, video_id)
    for message in messages:
        for url in re.findall(r'(https?://[^\s]+)', message.content):
            video_id = extract_video_id(url)
            if video_id:
                links.append((message, url, video_id))

    if not links:
        return

    # The video lookup, playlist creation, and playlist insert are all blocking YouTube API /
    # sqlite calls. Running them in threads keeps a slow response from stalling the bot's event
    # loop for every other user while a link is being processed.
    try:
        snippets = await asyncio.to_thread(get_video_snippets, [video_id for _, _, video_id in links])
    except QuotaExceededError:
        logger.warning("YouTube quota used up; skipping %d release links. Run /backfill-new-releases for them "
                       "after it resets.", len(links))
        return
    if snippets is None:
        logger.warning("No YouTube client available; skipping %d release links.", len(links))
        return

    reacted_messages = {}
    async with RELEASE_LOCK:
        for message, url, video_id in links:
            snippet = snippets.get(video_id)
            if not snippet:
                logger.warning("Could not fetch publish date for %s. Skipping.", video_id)
                continue

            processed = await asyncio.to_thread(
                _process_release_url, url, video_id, str(message.id), message.created_at,
                award_year_for(message.created_at), parse_publish_date(snippet)
            )
            if processed:
                reacted_messages[message.id] = message

    for message in reacted_messages.values():
        await message.add_reaction(EMOJI_IU)

def _process_release_url(url: str, video_id: str, message_id: str, msg_time: datetime,
                         award_year: int, publish_date: datetime) -> bool:
    """Synchronous worker: validates, stores, and syncs a single release URL to YouTube."""
    try:
        # If the video isn't from the current year, ignore it
        video_award_year = award_year_for(publish_date)
        if video_award_year != award_year:
            logger.info("Skipped %s: Video year (%s) does not match active year (%s).",
                        video_id, video_award_year, award_year)
            return False

        # Save to database initially as unprocessed (processed=0)
        added = add_new_release(video_id=video_id, original_url=url, message_id=message_id, msg_time=msg_time)
        if added is AddResult.DUPLICATE:
            return False

        # Check for existing playlist for this specific year
        playlist_id = get_playlist_id_for_year(award_year)

        # Create the playlist if it doesn't exist
        if not playlist_id:
            logger.info("Playlist for %s not found. Creating...", award_year)
            playlist_id = create_releases_playlist(award_year)
            if playlist_id:
                save_new_playlist(award_year, playlist_id)

        # Add video and mark as processed
        if playlist_id:
            success = add_video_to_playlist(playlist_id, video_id)
            if success:
                mark_release_processed(video_id)
                return True

        return False

    except Exception as ex:
        logger.error("Failed to process release %s: %s", video_id, ex)
        return False
