"""Builds Listen Game situations in a real (temporary) database, for tests of code that reads them.

Needs the `databases(Database.LISTEN_GAME)` fixture to have run first. Players take turns in the
order given, so the first player hosts round 1.
"""

import random
from unittest import mock

from db.listen_game import (
    RoundResult, close_round_db, create_game_db, get_current_round_db, get_ordered_players_db, register_player_db,
    save_round_results_db, set_round_theme_db, start_game_db, upsert_submission_db
)

GM, SUB_GM = 1, 2


def start_game(players: tuple[int, ...] = (101, 102, 103), max_round_days: int | None = None) -> int:
    """A started game in which `players` take turns in order. Returns the game id."""
    game_id = create_game_db(GM, SUB_GM, max_round_days)
    for user_id in players:
        register_player_db(game_id, user_id)
    with mock.patch.object(random, "shuffle", lambda items: None):
        assert start_game_db(game_id) is not None
    return game_id


def reveal_ready_round(game_id: int, results: list[tuple[int, str]] | None = None) -> int:
    """
    Takes the game's current round through theme, submissions and ranking, up to the moment the reveal
    starts (status `revealing`). `results` is [(user_id, title)] best first; by default every
    player except the host, ranked in the order they joined. Returns the round id.
    """
    game_round = get_current_round_db(game_id)
    if results is None:
        results = [(user_id, f"Song by {user_id}") for user_id in get_ordered_players_db(game_id)
                   if user_id != game_round.host_id]
    set_round_theme_db(game_round.round_id, "A theme")
    for user_id, title in results:
        upsert_submission_db(game_round.round_id, user_id, f"vid{user_id}", title)
    close_round_db(game_round.round_id)
    ranked = [RoundResult(user_id, rank, 10 - rank, f"Comment {rank}") for rank, (user_id, _) in enumerate(results, 1)]
    save_round_results_db(game_id, game_round.round_id, ranked)
    return game_round.round_id
