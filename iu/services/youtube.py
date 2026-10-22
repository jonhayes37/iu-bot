"""Service module for interacting with the YouTube Data API to manage playlists and videos."""

import os
import re
import logging
import threading
from typing import Any
from datetime import datetime
from google.auth.exceptions import GoogleAuthError
from google.oauth2.credentials import Credentials
from httplib2 import HttpLib2Error
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import youtube_token_path

logger = logging.getLogger('iu-bot')

# Robust RegEx that catches standard, mobile, embedded, and shortened YouTube URLs
YT_REGEX = re.compile(
    r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|'
    r'(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
)

class QuotaExceededError(Exception):
    """Exception raised when the YouTube Data API quota limit is reached."""

    def __init__(self, ex: Exception) -> None:
        ex_str = f"Quota exceeded: {ex}"
        super().__init__(ex_str)


class YouTubeUnavailableError(Exception):
    """
    The bot can't talk to YouTube at all: token.json is missing or no longer valid (it needs renewing,
    see docs/youtube.md), the network is down, or YouTube itself is failing. Raised instead of a
    "nothing found" result, so it isn't mistaken for a private video or an empty playlist.
    """


# Failures that say nothing about the request itself: the login or the connection is broken
_CONNECTION_ERRORS = (GoogleAuthError, HttpLib2Error, OSError)


def _error_reason(ex: HttpError) -> str:
    """Why the YouTube API refused a request, e.g. "quotaExceeded" or "videoNotFound"."""
    return ex.error_details[0].get('reason') if ex.error_details else "Unknown"


def _execute(request: Any, doing: str) -> dict:
    """
    Sends one API request. Raises QuotaExceededError when the daily quota is used up and
    YouTubeUnavailableError when YouTube can't be reached or won't accept the bot's login; any other
    refusal (a private video, a missing playlist) is raised as the HttpError for the caller to handle.
    """
    try:
        return request.execute()
    except HttpError as ex:
        if _error_reason(ex) == "quotaExceeded":
            logger.warning("YouTube API quota exceeded while %s!", doing)
            raise QuotaExceededError(ex) from ex
        if ex.resp.status == 401 or ex.resp.status >= 500:
            logger.error("YouTube is unavailable (HTTP %s) while %s: %s", ex.resp.status, doing, ex)
            raise YouTubeUnavailableError(ex) from ex
        raise
    except _CONNECTION_ERRORS as ex:
        logger.error("Could not reach YouTube while %s: %s", doing, ex)
        raise YouTubeUnavailableError(ex) from ex


class _YouTubeServiceCache:
    """Lazily builds one YouTube API client per thread.

    The client's underlying httplib2.Http object is not thread-safe, and calls arrive from the
    event loop thread and from asyncio.to_thread workers, so each thread keeps its own client.
    Worker threads are reused, so each one only builds its client once.
    """

    def __init__(self):
        self._local = threading.local()

    def get(self) -> Any:
        service = getattr(self._local, "service", None)
        if service is not None:
            return service

        token_path = youtube_token_path()
        if not token_path or not os.path.exists(token_path):
            logger.error("token.json missing at %s! Cannot authenticate.", token_path)
            raise YouTubeUnavailableError(f"token.json missing at {token_path}")

        try:
            creds = Credentials.from_authorized_user_file(token_path, ['https://www.googleapis.com/auth/youtube'])
        except ValueError as ex:  # not a usable token file (e.g. no refresh token)
            logger.error("token.json at %s can't be used: %s", token_path, ex)
            raise YouTubeUnavailableError(f"token.json at {token_path} can't be used: {ex}") from ex
        service = build('youtube', 'v3', credentials=creds)
        self._local.service = service
        return service

_yt_service_cache = _YouTubeServiceCache()

def get_yt_service() -> Any:
    """
    Returns this thread's YouTube API client, building it on first use. Raises
    YouTubeUnavailableError if there is no usable token.json.
    """
    return _yt_service_cache.get()

def create_playlist(title: str, description: str = "") -> str | None:
    """
    Creates an unlisted YouTube playlist with a custom title and returns its ID, or None if YouTube
    refused. Raises QuotaExceededError or YouTubeUnavailableError (see _execute).
    """
    youtube = get_yt_service()
    body = {
        "snippet": {"title": title, "description": description},
        "status": {"privacyStatus": "unlisted"}
    }

    try:
        req = youtube.playlists().insert(part="snippet,status", body=body) # pylint: disable=no-member
        response = _execute(req, "creating a playlist")
        logger.info("Created playlist '%s' with ID %s", title, response.get("id"))
        return response.get("id")
    except HttpError as ex:
        logger.error("Failed to create custom YouTube playlist: %s", ex)
        return None

def create_releases_playlist(year: int) -> str | None:
    """Creates an unlisted YouTube playlist for the given year and returns its ID."""
    title = f"{year} K-Pop Releases"
    description = f"Automated playlist for {year} K-Pop releases."
    return create_playlist(title, description)


def create_listen_game_playlist(host_name: str) -> str | None:
    """Creates an unlisted playlist for a Listen Game round."""
    title = f"Listen Game Round - {host_name}"
    description = "Automated playlist for the server Listen Game."
    return create_playlist(title, description)

# videos.list accepts up to 50 ids per request and costs 1 quota unit per request either way
VIDEOS_PER_REQUEST = 50

def get_video_snippets(video_ids: list[str]) -> dict[str, dict]:
    """
    Looks up the title, publish date and other details of many videos at once, 50 per request.

    Returns {video_id: snippet}. Videos that are private or deleted are missing from the result, and
    so are the videos of a request YouTube refused (it is logged). Raises QuotaExceededError when the
    daily quota is used up and YouTubeUnavailableError when YouTube can't be reached, so neither is
    mistaken for the videos being private or deleted.
    """
    youtube = get_yt_service()
    unique_ids = list(dict.fromkeys(video_ids))
    snippets = {}
    for start in range(0, len(unique_ids), VIDEOS_PER_REQUEST):
        batch = unique_ids[start:start + VIDEOS_PER_REQUEST]
        try:
            # Cost: 1 Quota Unit for the whole batch
            request = youtube.videos().list(part="snippet", id=",".join(batch)) # pylint: disable=no-member
            response = _execute(request, "looking up videos")
        except (QuotaExceededError, YouTubeUnavailableError):
            raise
        except Exception as ex:
            logger.error("YouTube API error fetching details for %d videos: %s", len(batch), ex)
            continue

        for item in response.get("items", []):
            snippets[item["id"]] = item["snippet"]

    return snippets

def parse_publish_date(snippet: dict) -> datetime:
    """The publish date from a video snippet. YouTube sends ISO 8601 like "2026-03-17T15:00:00Z"."""
    return datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))

def get_video_title(video_id: str) -> str | None:
    """
    Fetches the title of a YouTube video, or None if it is private, deleted or can't be read.
    Raises QuotaExceededError when the daily quota is used up and YouTubeUnavailableError when
    YouTube can't be reached.
    """
    snippet = get_video_snippets([video_id]).get(video_id)
    return snippet["title"] if snippet else None

def remove_video_from_playlist(playlist_id: str, video_id: str) -> bool:
    """
    Finds and removes a specific video from a playlist. Returns False if YouTube refused (including a
    used-up quota); raises YouTubeUnavailableError when YouTube can't be reached.
    """
    youtube = get_yt_service()
    try:
        # Ask YouTube for the playlistItemId of this specific video
        request = youtube.playlistItems().list( # pylint: disable=no-member
            part="id",
            playlistId=playlist_id,
            videoId=video_id
        )
        response = _execute(request, "finding a video in a playlist")
        items = response.get("items", [])

        if not items:
            return True

        playlist_item_id = items[0]["id"]

        # Delete the item using that ID
        _execute(youtube.playlistItems().delete(id=playlist_item_id), "removing a video") # pylint: disable=no-member
        return True
    except (HttpError, QuotaExceededError) as ex:
        logger.error("Failed to remove video %s from playlist: %s", video_id, ex)
        return False

def extract_video_id(url: str) -> str | None:
    """Safely extracts a YouTube video ID from various URL formats."""
    match = YT_REGEX.search(url)
    if not match:
        return None

    return match.group(1)

def get_playlist_video_ids(playlist_id: str) -> set[str] | None:
    """
    Fetches all video IDs currently present in a YouTube playlist.

    Returns None if the playlist couldn't be read, so a failure can't be mistaken for an empty
    playlist. Raises QuotaExceededError when the daily API quota is used up and
    YouTubeUnavailableError when YouTube can't be reached.
    """
    youtube = get_yt_service()
    video_ids = set()
    try:
        # maxResults=50 is the maximum allowed per page by the YouTube API
        request = youtube.playlistItems().list( # pylint: disable=no-member
            part="snippet",
            playlistId=playlist_id,
            maxResults=50
        )

        while request is not None:
            response = _execute(request, f"reading playlist {playlist_id}")
            for item in response.get("items", []):
                video_ids.add(item["snippet"]["resourceId"]["videoId"])

            # Paginate if the playlist has more than 50 items
            request = youtube.playlistItems().list_next(request, response) # pylint: disable=no-member

        return video_ids
    except HttpError as ex:
        logger.error("Failed to fetch playlist items for %s: %s", playlist_id, ex)
        return None

def add_video_to_playlist(playlist_id: str, video_id: str) -> bool:
    """
    Adds a video to the specified playlist. Returns True if successful, False if YouTube refused.
    Raises QuotaExceededError or YouTubeUnavailableError (see _execute).
    """
    youtube = get_yt_service()
    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id}
        }
    }

    try:
        req = youtube.playlistItems().insert(part="snippet", body=body) # pylint: disable=no-member
        _execute(req, "adding a video")
        return True
    except HttpError as ex:
        if _error_reason(ex) == "videoNotFound":
            logger.warning("Video %s cannot be added (it may be private or deleted).", video_id)
        else:
            logger.error("Failed to add video %s: %s", video_id, ex)
        return False

def contains_youtube_url(text: str) -> bool:
    """Checks if a string contains a valid YouTube URL."""
    return bool(YT_REGEX.search(text))
