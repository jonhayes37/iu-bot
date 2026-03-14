"""Service module for interacting with the YouTube Data API to manage playlists and videos."""

import os
import logging
from typing import Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger('iu-bot')

TOKEN_PATH = os.getenv('TOKEN_DIR')

def get_yt_service() -> Any:
    if not os.path.exists(TOKEN_PATH):
        logger.error("token.json missing at %s! Cannot authenticate.", TOKEN_PATH)
        return None

    creds = Credentials.from_authorized_user_file(TOKEN_PATH, ['https://www.googleapis.com/auth/youtube'])
    return build('youtube', 'v3', credentials=creds)

def create_playlist(year: int) -> str | None:
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
    except HttpError as e:
        logger.error("Failed to create YouTube playlist: %s", e)
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
    except HttpError as e:
        # Catch specific API errors like Quota Limits or Deleted Videos
        error_reason = e.error_details[0].get('reason') if e.error_details else "Unknown"
        if error_reason == "quotaExceeded":
            logger.warning("YouTube API Quota exceeded! Will process remaining videos tomorrow.")
        elif error_reason == "videoNotFound":
            logger.warning("Video %s cannot be added (it may be private or deleted).", video_id)
        else:
            logger.error("Failed to add video %s: %s", video_id, e)
        return False
