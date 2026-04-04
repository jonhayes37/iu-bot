"""Service module for interacting with the YouTube Data API to manage playlists and videos."""

import os
import re
import logging
from typing import Any
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger('iu-bot')

# Robust RegEx that catches standard, mobile, embedded, and shortened YouTube URLs
YT_REGEX = re.compile(
    r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|'
    r'(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
)
TOKEN_PATH = os.getenv('TOKEN_DIR')

class QuotaExceededError(Exception):
    """Exception raised when the YouTube Data API quota limit is reached."""

    def __init__(self, ex: Exception) -> None:
        ex_str = f"Quota exceeded: {ex}"
        super().__init__(ex_str)


def get_yt_service() -> Any:
    if not os.path.exists(TOKEN_PATH):
        logger.error("token.json missing at %s! Cannot authenticate.", TOKEN_PATH)
        return None

    creds = Credentials.from_authorized_user_file(TOKEN_PATH, ['https://www.googleapis.com/auth/youtube'])
    return build('youtube', 'v3', credentials=creds)

def create_releases_playlist(year: int) -> str | None:
    """Creates an unlisted YouTube playlist and returns its ID."""
    youtube = get_yt_service()
    if not youtube:
        return None

    title = f"{year} K-Pop Releases"
    body = {
        "snippet": {"title": title, "description": f"Automated playlist for {year} K-Pop releases."},
        "status": {"privacyStatus": "unlisted"}
    }

    try:
        req = youtube.playlists().insert(part="snippet,status", body=body) # pylint: disable=no-member
        response = req.execute()
        logger.info("Created playlist '%s' with ID %s:\n%s", title, response.get("id"), response)
        return response.get("id")
    except HttpError as ex:
        logger.error("Failed to create YouTube playlist: %s", ex)
        return None

def get_video_publish_date(video_id: str) -> datetime | None:
    """Fetches the publish date of a video and returns a datetime object."""
    youtube = get_yt_service()
    if not youtube:
        return False

    try:
        # Cost: 1 Quota Unit
        request = youtube.videos().list(  # pylint: disable=no-member
            part="snippet",
            id=video_id
        )
        response = request.execute()

        items = response.get("items", [])
        if not items:
            return None # Video might be deleted or private

        # YouTube returns ISO 8601 format: "2026-03-17T15:00:00Z"
        raw_date_str = items[0]["snippet"]["publishedAt"]
        clean_date_str = raw_date_str.replace("Z", "+00:00")
        publish_date = datetime.fromisoformat(clean_date_str)
        return publish_date

    except Exception as ex:
        logger.error("YouTube API error fetching date for %s: %s", video_id, ex)
        return None

def get_video_title(video_id: str) -> str | None:
    """Fetches the title of a YouTube video for fuzzy matching."""
    youtube = get_yt_service()
    if not youtube:
        return None

    try:
        request = youtube.videos().list(part="snippet", id=video_id) # pylint: disable=no-member
        response = request.execute()
        items = response.get("items", [])
        if not items:
            return None
        return items[0]["snippet"]["title"]
    except Exception as ex:
        logger.error("YouTube API error fetching title for %s: %s", video_id, ex)
        return None

def remove_video_from_playlist(playlist_id: str, video_id: str) -> bool:
    """Finds and removes a specific video from a playlist."""
    youtube = get_yt_service()
    if not youtube:
        return False

    try:
        # Ask YouTube for the playlistItemId of this specific video
        request = youtube.playlistItems().list( # pylint: disable=no-member
            part="id",
            playlistId=playlist_id,
            videoId=video_id
        )
        response = request.execute()
        items = response.get("items", [])

        if not items:
            return True

        playlist_item_id = items[0]["id"]

        # Delete the item using that ID
        youtube.playlistItems().delete(id=playlist_item_id).execute() # pylint: disable=no-member
        return True
    except HttpError as ex:
        logger.error("Failed to remove video %s from playlist: %s", video_id, ex)
        return False

def extract_video_id(url: str) -> str | None:
    """Safely extracts a YouTube video ID from various URL formats."""
    match = YT_REGEX.search(url)
    if not match:
        return None

    return match.group(1)

def get_playlist_video_ids(playlist_id: str) -> set[str]:
    """Fetches all video IDs currently present in a YouTube playlist."""
    youtube = get_yt_service()
    if not youtube:
        return set()

    video_ids = set()
    try:
        # maxResults=50 is the maximum allowed per page by the YouTube API
        request = youtube.playlistItems().list( # pylint: disable=no-member
            part="snippet",
            playlistId=playlist_id,
            maxResults=50
        )

        while request is not None:
            response = request.execute()
            for item in response.get("items", []):
                video_ids.add(item["snippet"]["resourceId"]["videoId"])

            # Paginate if the playlist has more than 50 items
            request = youtube.playlistItems().list_next(request, response) # pylint: disable=no-member

        return video_ids
    except HttpError as ex:
        logger.error("Failed to fetch playlist items for %s: %s", playlist_id, ex)
        return set()

def create_listen_game_playlist(host_name: str) -> str | None:
    """Creates an unlisted playlist for a Listen Game round."""
    youtube = get_yt_service()
    if not youtube:
        return None

    title = f"Listen Game Round - {host_name}"
    body = {
        "snippet": {"title": title, "description": "Automated playlist for the server Listen Game."},
        "status": {"privacyStatus": "unlisted"}
    }

    try:
        req = youtube.playlists().insert(part="snippet,status", body=body) # pylint: disable=no-member
        response = req.execute()
        return response.get("id")
    except HttpError as ex:
        error_reason = ex.error_details[0].get('reason') if ex.error_details else "Unknown"
        if error_reason == "quotaExceeded":
            logger.warning("YouTube API Quota exceeded during playlist creation!")
            raise QuotaExceededError(ex) from ex
        logger.error("Failed to create Listen Game playlist: %s", ex)
        return None

def add_video_to_playlist(playlist_id: str, video_id: str) -> bool:
    """Adds a video to the specified playlist. Returns True if successful."""
    youtube = get_yt_service()
    if not youtube:
        return False

    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id}
        }
    }

    try:
        req = youtube.playlistItems().insert(part="snippet", body=body) # pylint: disable=no-member
        req.execute()
        return True
    except HttpError as ex:
        error_reason = ex.error_details[0].get('reason') if ex.error_details else "Unknown"
        if error_reason == "quotaExceeded":
            logger.warning("YouTube API Quota exceeded during video addition!")
            raise QuotaExceededError(ex) from ex
        elif error_reason == "videoNotFound":
            logger.warning("Video %s cannot be added (it may be private or deleted).", video_id)
        else:
            logger.error("Failed to add video %s: %s", video_id, ex)
        return False

def contains_youtube_url(text: str) -> bool:
    """Checks if a string contains a valid YouTube URL."""
    return bool(YT_REGEX.search(text))
