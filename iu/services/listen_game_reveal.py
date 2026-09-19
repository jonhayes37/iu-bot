"""Public, resumable reveal of a listen game round's rankings.

Once a host confirms their rankings, the round moves to 'revealing' and the points are already
saved. The reveal then posts messages to the channel over several minutes. Progress is stored in
listen_rounds.reveal_step after every message, so if the bot restarts mid-reveal it carries on
where it left off instead of starting over (or scoring the round a second time).

reveal_step values:
    0                     nothing posted yet
    1                     the intro message is posted
    1 + k                 the k-th song reveal (worst rank first) is posted
    len(songs) + 2        the round summary and current standings are posted
    len(songs) + 3        the game-over messages are posted (only used after the last turn)
"""

import asyncio
import logging

import discord

from db.listen_game import (
    advance_game_turn_db, get_game_leaderboard_db, get_game_rounds_db, get_next_host_id_db,
    get_round_results_db, get_round_reveal_state_db, set_reveal_step_db
)
from utils.strings import generate_leaderboard_text, get_ordinal

logger = logging.getLogger('iu-bot')

REVEAL_DELAY_SECONDS = 15

_active_reveals: set[int] = set()
_reveal_tasks: set[asyncio.Task] = set()


def start_reveal(channel: discord.TextChannel, round_id: int) -> bool:
    """
    Starts (or resumes) the reveal for a round in the background.
    Returns False if a reveal for this round is already running in this process.
    """
    if round_id in _active_reveals:
        return False

    _active_reveals.add(round_id)
    task = asyncio.create_task(_run_reveal(channel, round_id))
    _reveal_tasks.add(task)
    task.add_done_callback(_reveal_tasks.discard)
    return True


async def _run_reveal(channel: discord.TextChannel, round_id: int):
    try:
        await _reveal(channel, round_id)
    except Exception:
        logger.exception("Reveal for round %s stopped early; it will resume from where it left off.", round_id)
    finally:
        _active_reveals.discard(round_id)


async def _reveal(channel: discord.TextChannel, round_id: int):
    state = get_round_reveal_state_db(round_id)
    if not state or state['status'] != 'revealing':
        logger.info("Round %s is not waiting on a reveal; nothing to do.", round_id)
        return

    game_id = state['game_id']
    step = state['reveal_step']
    results = get_round_results_db(round_id)
    reveal_order = list(reversed(results))
    summary_step = len(reveal_order) + 2
    game_over_step = summary_step + 1

    if step < 1:
        player_role = discord.utils.get(channel.guild.roles, name='Listen Game Player')
        role_text = f"{player_role.mention}, " if player_role else ""
        await channel.send(f"🎧 **{role_text}<@{state['host_id']}> has finished their rankings! "
                           "Here are the results:**")
        step = 1
        set_reveal_step_db(round_id, step)
        await asyncio.sleep(REVEAL_DELAY_SECONDS)

    for index, result in enumerate(reveal_order, start=1):
        if step >= index + 1:
            continue

        url = f"https://youtu.be/{result['video_id']}"
        await channel.send(
            f"**{get_ordinal(result['rank'])}: [{result['raw_title']}](<{url}>)**\n{result['commentary']}"
        )
        step = index + 1
        set_reveal_step_db(round_id, step)
        await asyncio.sleep(REVEAL_DELAY_SECONDS)

    # None means this was the last turn (the lookup raises on errors, so it can't mean "failed")
    next_host_id = get_next_host_id_db(game_id, round_id)

    if step < summary_step:
        await channel.send(_build_round_summary(results, get_game_leaderboard_db(game_id), next_host_id))
        step = summary_step
        set_reveal_step_db(round_id, step)

    if not next_host_id and step < game_over_step:
        await _post_game_over(channel, game_id)
        set_reveal_step_db(round_id, game_over_step)

    if not advance_game_turn_db(game_id, round_id):
        raise RuntimeError(f"Could not advance game {game_id} after round {round_id}")


def _build_round_summary(results: list[dict], leaderboard: list[dict], next_host_id: int | None) -> str:
    summary_lines = ["**Last Round's Results**"]
    for result in results:
        summary_lines.append(
            f"{get_ordinal(result['rank'])}: <@{result['user_id']}> - **{result['raw_title']}** "
            f"({result['points']} pts)"
        )

    ranking_lines = ["**Current Ranking**"]
    if leaderboard:
        for index, entry in enumerate(leaderboard, start=1):
            ranking_lines.append(f"{get_ordinal(index)} - <@{entry['user_id']}> ({entry['score']} pts)")
    else:
        ranking_lines.append("*Error fetching leaderboard.*")

    message = "🎉 **Round complete!**\n\n" + "\n".join(summary_lines) + "\n\n" + "\n".join(ranking_lines) + "\n\n"
    if next_host_id:
        message += f"The next listener is <@{next_host_id}>! Use `/listen-game-post-ruleset` " \
            "when you are ready to begin."
    return message


async def _post_game_over(channel: discord.TextChannel, game_id: int):
    await channel.send(generate_leaderboard_text(get_game_leaderboard_db(game_id)))

    rounds = get_game_rounds_db(game_id)
    if not rounds:
        return

    playlist_lines = ["🎶 **Here's all of the playlists from this game:**"]
    for index, round_data in enumerate(rounds, start=1):
        if round_data['playlist_id']:
            playlist_url = f"https://www.youtube.com/playlist?list={round_data['playlist_id']}"
        else:
            playlist_url = "*No playlist generated*"
        playlist_lines.append(f"**Round {index}** (<@{round_data['host_id']}>): {playlist_url}")

    # A short pause so this posts cleanly after the leaderboard
    await asyncio.sleep(2)
    await channel.send("\n".join(playlist_lines))
