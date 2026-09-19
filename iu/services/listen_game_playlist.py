"""Adds a listen game submission to the round's YouTube playlist, creating the playlist if needed."""

import asyncio
import enum
import logging

import discord

from db.listen_game import Round, update_round_playlist_db
from services.youtube import (
    QuotaExceededError, add_video_to_playlist, create_listen_game_playlist, remove_video_from_playlist
)

logger = logging.getLogger('iu-bot')

# The YouTube calls run in worker threads so they don't freeze the bot, which means other commands
# can run while one is waiting. Only one submission is processed at a time so that the "already
# claimed" check, the playlist update and the save can't interleave between two players.
SUBMISSION_LOCK = asyncio.Lock()


class PlaylistOutcome(enum.Enum):
    """What happened when a song was put into the round's playlist."""
    ADDED = "added"
    QUOTA_EXCEEDED = "quota_exceeded"
    CREATE_FAILED = "create_failed"
    ADD_FAILED = "add_failed"


def get_host_name(guild: discord.Guild, host_id: int) -> str:
    """The listener's display name, for naming the round's playlist. Call this on the event loop."""
    host_member = guild.get_member(host_id)
    return host_member.display_name if host_member else "Unknown"


def put_song_in_round_playlist(
    host_name: str, active_round: Round, video_id: str, previous_video_id: str | None = None
) -> tuple[PlaylistOutcome, str | None]:
    """
    Adds video_id to the round's playlist. The round's playlist is created first if it doesn't exist
    yet (and saved on active_round). If the player is replacing an earlier song, that song is removed.

    Blocking (YouTube API calls): run it with asyncio.to_thread. Returns the outcome and the
    playlist ID, which is None only if the playlist could not be created.
    """
    playlist_id = active_round.playlist_id
    try:
        if playlist_id and previous_video_id:
            if not remove_video_from_playlist(playlist_id, previous_video_id):
                logger.warning("Failed to remove old video %s during swap.", previous_video_id)

        if not playlist_id:
            playlist_id = create_listen_game_playlist(host_name)
            if not playlist_id:
                return PlaylistOutcome.CREATE_FAILED, None
            update_round_playlist_db(active_round.round_id, playlist_id)
            active_round.playlist_id = playlist_id

        if not add_video_to_playlist(playlist_id, video_id):
            return PlaylistOutcome.ADD_FAILED, playlist_id

    except QuotaExceededError:
        return PlaylistOutcome.QUOTA_EXCEEDED, playlist_id

    return PlaylistOutcome.ADDED, playlist_id
