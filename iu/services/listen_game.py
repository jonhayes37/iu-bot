"""Building blocks shared by the listen game commands: loading the current round, DMs, and the tracker."""

import logging
from dataclasses import dataclass

import discord

from db.listen_game import (
    Game, GameStatus, Round, RoundStatus, get_current_round_db, get_game_by_status_db,
    get_registered_players_db, get_round_submissions_db
)

logger = logging.getLogger('iu-bot')

NO_ACTIVE_GAME = "⚠️ There is no active game right now."
NO_ACTIVE_ROUND = "⚠️ Could not find an active round."


@dataclass
class RoundContext:
    """The game that is being played and the round that is currently in play."""
    game: Game
    round: Round


async def _reply(interaction: discord.Interaction, text: str, deferred: bool):
    if deferred:
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


async def require_active_round(interaction: discord.Interaction, *, deferred: bool,
                               statuses: tuple[RoundStatus, ...] | None = None,
                               wrong_status_message: str | None = None) -> RoundContext | None:
    """
    Loads the game being played and its current round, for a command that needs them. If there is
    no game, no round, or the round isn't in one of `statuses`, tells the user why and returns None,
    so a command starts with `if not ctx: return`.

    deferred says whether the command has already deferred its response (so replies use followup).
    """
    game = get_game_by_status_db(GameStatus.PLAYING)
    if not game:
        await _reply(interaction, NO_ACTIVE_GAME, deferred)
        return None

    active_round = get_current_round_db(game.game_id)
    if not active_round:
        await _reply(interaction, NO_ACTIVE_ROUND, deferred)
        return None

    if statuses and active_round.status not in statuses:
        await _reply(interaction, wrong_status_message or "⚠️ The round isn't in the right phase for that.", deferred)
        return None

    return RoundContext(game, active_round)


async def send_dm(client: discord.Client, user_id: int, content: str) -> bool:
    """DMs a user. Returns False, after logging why, if they can't be messaged (closed DMs, deleted account)."""
    try:
        user = client.get_user(user_id) or await client.fetch_user(user_id)
        await user.send(content)
        return True
    except discord.Forbidden:
        logger.warning("Could not DM user %s (their DMs are closed).", user_id)
    except discord.HTTPException as ex:
        logger.warning("Could not DM user %s: %s", user_id, ex)
    return False


def playlist_link(playlist_id: str | None) -> str:
    """The YouTube link for a round's playlist, or a note that there isn't one."""
    return f"https://www.youtube.com/playlist?list={playlist_id}" if playlist_id else "No playlist generated."


async def update_submission_tracker(channel: discord.abc.Messageable, ctx: RoundContext, extra_text: str = ""):
    """Refreshes the live "x/y submissions" message that the ruleset post is followed by."""
    if not ctx.round.status_message_id:
        return

    total_needed = len(get_registered_players_db(ctx.game.game_id)) - 1
    submitted = len(get_round_submissions_db(ctx.round.round_id))
    text = f"🎧 **Round Status:** We are at `{submitted}/{total_needed}` submissions for the round.{extra_text}"
    try:
        tracker_message = await channel.fetch_message(ctx.round.status_message_id)
        await tracker_message.edit(content=text)
    except (discord.NotFound, discord.Forbidden) as ex:
        logger.warning("Could not update the submissions tracker message: %s", ex)
