"""Database logic for the listen game.

State machine. A game is `registration` -> `playing` -> `finished`. Each round of a game is:

    setting_theme -> submitting -> ranking -> revealing -> completed

and the GM can `skip` a round that is in any of its first three states.

Every status change is one guarded UPDATE (`WHERE status IN (...)`), so a stale or repeated request
can't move a game or round somewhere it shouldn't. Functions that move state return whether it
moved (False means it was no longer in a state that allows the move); skipping a round raises
InvalidStateError instead, since callers only do it after checking. See db/connection.py for the
error contract shared by all of db/.
"""
import enum
import random
import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from config import Database
from db.connection import db_connection
from db.errors import InvalidStateError
from utils.timestamps import parse_db_timestamp


class GameStatus(enum.StrEnum):
    """Where a game is in its life."""
    REGISTRATION = "registration"
    PLAYING = "playing"
    FINISHED = "finished"


class RoundStatus(enum.StrEnum):
    """Where a round is in its life."""
    SETTING_THEME = "setting_theme"
    SUBMITTING = "submitting"
    RANKING = "ranking"
    REVEALING = "revealing"
    COMPLETED = "completed"
    SKIPPED = "skipped"


# Rounds that can still be skipped by the GM (results not yet being revealed)
SKIPPABLE_ROUND_STATUSES = (RoundStatus.SETTING_THEME, RoundStatus.SUBMITTING, RoundStatus.RANKING)
# Rounds that are still in play
LIVE_ROUND_STATUSES = (RoundStatus.SETTING_THEME, RoundStatus.SUBMITTING, RoundStatus.RANKING,
                       RoundStatus.REVEALING)


class SaveResult(enum.Enum):
    """Outcome of saving a round's rankings."""
    SAVED = "saved"
    NOT_IN_RANKING = "not_in_ranking"


class SwapOutcome(enum.Enum):
    """Outcome of swapping two players' turn order."""
    SWAPPED = "swapped"
    NO_ACTIVE_HOST = "no_active_host"
    PLAYER_NOT_IN_GAME = "player_not_in_game"
    NOT_AFTER_HOST = "not_after_host"


def _row_to_fields(cls, row: sqlite3.Row) -> dict:
    """The columns of a query row that match the dataclass's fields."""
    columns = row.keys()
    return {f.name: row[f.name] for f in fields(cls) if f.name in columns}


@dataclass
class Game:
    """A row of listen_games."""
    game_id: int
    gm_id: int
    sub_gm_id: int
    status: GameStatus
    started_at: str | None = None
    max_round_days: int | None = None
    game_start_message_id: int | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Game":
        """Builds a Game from a `SELECT * FROM listen_games` row."""
        game = cls(**_row_to_fields(cls, row))
        game.status = GameStatus(game.status)
        return game


@dataclass
class Round:
    """A row of listen_rounds."""
    round_id: int
    game_id: int
    host_id: int
    status: RoundStatus
    theme: str | None = None
    playlist_id: str | None = None
    started_at: str | None = None
    status_message_id: int | None = None
    ruleset_message_id: int | None = None
    reveal_step: int = 0

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Round":
        """Builds a Round from a `SELECT * FROM listen_rounds` row."""
        listen_round = cls(**_row_to_fields(cls, row))
        listen_round.status = RoundStatus(listen_round.status)
        return listen_round


@dataclass
class Submission:
    """A row of listen_submissions: one player's song for a round (and its ranking once ranked)."""
    round_id: int
    user_id: int
    video_id: str
    raw_title: str
    submitted_at: str | None = None
    rank: int | None = None
    points_awarded: int = 0
    commentary: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Submission":
        """Builds a Submission from a `SELECT * FROM listen_submissions` row."""
        return cls(**_row_to_fields(cls, row))


@dataclass
class Standing:
    """A player's total score in a game."""
    user_id: int
    score: int


@dataclass
class PendingPlayer:
    """A player who hasn't submitted a song for the round that is currently open."""
    user_id: int
    game_id: int
    round_id: int
    started_at: str
    last_reminded_at: str | None = None
    ruleset_message_id: int | None = None
    max_round_days: int | None = None


@dataclass
class RankingPick:
    """One song the listener has ranked so far, saved before the results are confirmed."""
    user_id: int
    rank: int
    commentary: str


@dataclass
class RoundResult:
    """A ranking to save: which player's song came in at which rank, for how many points."""
    user_id: int
    rank: int
    points: int
    commentary: str


# ---------------------------------------------------------------------------------------------
# Guarded status changes
# ---------------------------------------------------------------------------------------------

def _in_list(values) -> str:
    """The SQL for a `status IN (...)` list. Only ever given the enum members above, never user input."""
    return ", ".join(f"'{value.value}'" for value in values)


def _move_round(cursor: sqlite3.Cursor, round_id: int, new_status: RoundStatus,
                allowed_from: tuple[RoundStatus, ...], extra_assignments: str = "") -> bool:
    """Changes a round's status if (and only if) it is currently in one of `allowed_from`."""
    cursor.execute(f"""
        UPDATE listen_rounds SET status = ?{extra_assignments}
        WHERE round_id = ? AND status IN ({_in_list(allowed_from)})
    """, (new_status.value, round_id))
    return cursor.rowcount > 0


def _move_game(cursor: sqlite3.Cursor, game_id: int, new_status: GameStatus,
               allowed_from: tuple[GameStatus, ...]) -> bool:
    """Changes a game's status if (and only if) it is currently in one of `allowed_from`."""
    cursor.execute(f"""
        UPDATE listen_games SET status = ?
        WHERE game_id = ? AND status IN ({_in_list(allowed_from)})
    """, (new_status.value, game_id))
    return cursor.rowcount > 0


def _start_round(cursor: sqlite3.Cursor, game_id: int, host_id: int):
    """Creates a round for the host, waiting for them to post their ruleset."""
    cursor.execute("""
        INSERT INTO listen_rounds (game_id, host_id, status)
        VALUES (?, ?, ?)
    """, (game_id, host_id, RoundStatus.SETTING_THEME.value))


def _find_next_host_id(cursor: sqlite3.Cursor, game_id: int, round_id: int) -> int | None:
    """Returns the host of the round after this one, or None if this was the last turn."""
    cursor.execute("""
        SELECT p.turn_order
        FROM listen_rounds r
        JOIN listen_players p ON r.host_id = p.user_id AND r.game_id = p.game_id
        WHERE r.round_id = ?
    """, (round_id,))
    host_row = cursor.fetchone()
    if not host_row:
        raise InvalidStateError(f"The host of round {round_id} is not a player in game {game_id}")

    cursor.execute("""
        SELECT user_id
        FROM listen_players
        WHERE game_id = ? AND turn_order > ?
        ORDER BY turn_order ASC LIMIT 1
    """, (game_id, host_row[0]))
    next_row = cursor.fetchone()
    return next_row[0] if next_row else None


# ---------------------------------------------------------------------------------------------
# Games and players
# ---------------------------------------------------------------------------------------------

def create_game_db(gm_id: int, sub_gm_id: int, max_round_days: int | None) -> int | None:
    """Creates a new game in the registration state. Returns its ID, or None if a game is already running."""
    with db_connection(Database.LISTEN_GAME) as conn:
        # Take the write lock first, so two people creating a game at once can't both pass the check
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()

        cursor.execute("SELECT game_id FROM listen_games WHERE status != ?", (GameStatus.FINISHED.value,))
        if cursor.fetchone():
            return None

        cursor.execute("""
            INSERT INTO listen_games (gm_id, sub_gm_id, status, max_round_days)
            VALUES (?, ?, ?, ?)
        """, (gm_id, sub_gm_id, GameStatus.REGISTRATION.value, max_round_days))

        return cursor.lastrowid

def start_game_db(game_id: int) -> list[int] | None:
    """
    Starts a game that is in registration: randomizes the turn order and sets up Round 1.
    Returns the players in turn order, or None if the game can't be started (not in registration,
    or fewer than 2 players).
    """
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()

        # Fetch current players who registered via the UI
        cursor.execute("SELECT user_id FROM listen_players WHERE game_id = ?", (game_id,))
        players = [row[0] for row in cursor.fetchall()]

        if len(players) < 2 or not _move_game(cursor, game_id, GameStatus.PLAYING, (GameStatus.REGISTRATION,)):
            return None

        random.shuffle(players)

        # Update turn orders natively in the DB
        for order, uid in enumerate(players):
            cursor.execute("""
                UPDATE listen_players SET turn_order = ?
                WHERE game_id = ? AND user_id = ?
            """, (order, game_id, uid))

        _start_round(cursor, game_id, players[0])
        return players

def get_game_by_status_db(status: GameStatus) -> Game | None:
    """Fetches a game record based on its current phase."""
    with db_connection(Database.LISTEN_GAME, row_factory=True) as conn:
        row = conn.execute("SELECT * FROM listen_games WHERE status = ?", (status.value,)).fetchone()
        return Game.from_row(row) if row else None

def register_player_db(game_id: int, user_id: int) -> bool:
    """Adds a player to a game. Returns True if added, False if they already joined."""
    with db_connection(Database.LISTEN_GAME) as conn:
        # Score and turn_order default to 0/NULL
        added = conn.execute("""
            INSERT OR IGNORE INTO listen_players (game_id, user_id, score)
            VALUES (?, ?, 0)
        """, (game_id, user_id)).rowcount
        return added > 0

def unregister_player_db(game_id: int, user_id: int) -> bool:
    """Removes a player from a game during registration."""
    with db_connection(Database.LISTEN_GAME) as conn:
        removed = conn.execute(
            "DELETE FROM listen_players WHERE game_id = ? AND user_id = ?", (game_id, user_id)
        ).rowcount
        return removed > 0

def get_registered_players_db(game_id: int) -> list[int]:
    """Returns a list of user_ids registered for the game."""
    with db_connection(Database.LISTEN_GAME) as conn:
        return [row[0] for row in conn.execute("SELECT user_id FROM listen_players WHERE game_id = ?", (game_id,))]

def get_ordered_players_db(game_id: int) -> list[int]:
    """Returns a list of user_ids ordered by their current turn order."""
    with db_connection(Database.LISTEN_GAME) as conn:
        rows = conn.execute(
            "SELECT user_id FROM listen_players WHERE game_id = ? ORDER BY turn_order ASC", (game_id,)
        )
        return [row[0] for row in rows]

def remove_player_from_game_db(game_id: int, user_id: int) -> bool:
    """Removes a player from the active game roster."""
    with db_connection(Database.LISTEN_GAME) as conn:
        removed = conn.execute(
            "DELETE FROM listen_players WHERE game_id = ? AND user_id = ?", (game_id, user_id)
        ).rowcount
        return removed > 0

def get_game_leaderboard_db(game_id: int) -> list[Standing]:
    """Fetches the scores for all players in a game, sorted highest to lowest."""
    with db_connection(Database.LISTEN_GAME) as conn:
        rows = conn.execute(
            "SELECT user_id, score FROM listen_players WHERE game_id = ? ORDER BY score DESC", (game_id,)
        )
        return [Standing(user_id=row[0], score=row[1]) for row in rows]

def swap_player_orders_db(game_id: int, user_id1: int, user_id2: int) -> SwapOutcome:
    """Swaps the turn order of two players if they are both later in the order than the current host."""
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()

        # 1. Find the current host's turn order using the active round
        cursor.execute(f"""
            SELECT p.turn_order
            FROM listen_rounds r
            JOIN listen_players p ON r.host_id = p.user_id AND r.game_id = p.game_id
            WHERE r.game_id = ? AND r.status IN ({_in_list(LIVE_ROUND_STATUSES)})
            ORDER BY r.round_id DESC LIMIT 1
        """, (game_id,))
        host_row = cursor.fetchone()
        if not host_row:
            return SwapOutcome.NO_ACTIVE_HOST

        # 2. Get the turn orders for both target players
        cursor.execute("SELECT turn_order FROM listen_players WHERE game_id = ? AND user_id = ?",
                       (game_id, user_id1))
        p1_row = cursor.fetchone()
        cursor.execute("SELECT turn_order FROM listen_players WHERE game_id = ? AND user_id = ?",
                       (game_id, user_id2))
        p2_row = cursor.fetchone()
        if not p1_row or not p2_row:
            return SwapOutcome.PLAYER_NOT_IN_GAME
        p1_turn, p2_turn = p1_row[0], p2_row[0]

        # 3. Check if both turn orders are strictly greater than the current host's position
        if p1_turn <= host_row[0] or p2_turn <= host_row[0]:
            return SwapOutcome.NOT_AFTER_HOST

        # 4. Swap their positions
        cursor.execute("UPDATE listen_players SET turn_order = ? WHERE game_id = ? AND user_id = ?",
                       (p2_turn, game_id, user_id1))
        cursor.execute("UPDATE listen_players SET turn_order = ? WHERE game_id = ? AND user_id = ?",
                       (p1_turn, game_id, user_id2))
        return SwapOutcome.SWAPPED

def get_active_gm_id(game: Game, active_round: Round | None = None) -> int:
    """Determines who should act as GM for the current round."""
    # If the primary GM is the listener this round, the substitute GM runs it
    if active_round and active_round.host_id == game.gm_id:
        return game.sub_gm_id
    return game.gm_id

def update_game_start_message_db(game_id: int, message_id: int) -> None:
    """Saves the message ID of the game start (turn order) post."""
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("UPDATE listen_games SET game_start_message_id = ? WHERE game_id = ?", (message_id, game_id))


# ---------------------------------------------------------------------------------------------
# Rounds
# ---------------------------------------------------------------------------------------------

def get_current_round_db(game_id: int) -> Round | None:
    """Fetches the round that is currently in play for a game."""
    with db_connection(Database.LISTEN_GAME, row_factory=True) as conn:
        row = conn.execute(f"""
            SELECT * FROM listen_rounds
            WHERE game_id = ? AND status IN ({_in_list(LIVE_ROUND_STATUSES)})
            ORDER BY round_id DESC LIMIT 1
        """, (game_id,)).fetchone()
        return Round.from_row(row) if row else None

def get_game_rounds_db(game_id: int) -> list[Round]:
    """Fetches all rounds for a given game, oldest first, to compile the playlists."""
    with db_connection(Database.LISTEN_GAME, row_factory=True) as conn:
        rows = conn.execute("SELECT * FROM listen_rounds WHERE game_id = ? ORDER BY round_id ASC", (game_id,))
        return [Round.from_row(row) for row in rows]

def set_round_theme_db(round_id: int, theme: str) -> bool:
    """
    Saves the theme and starts the timer. A round waiting for its ruleset moves on to `submitting`;
    one that is already accepting submissions just gets the new ruleset. Returns False if the round
    is past both of those.
    """
    with db_connection(Database.LISTEN_GAME) as conn:
        updated = conn.execute(f"""
            UPDATE listen_rounds
            SET theme = ?, status = ?, started_at = CURRENT_TIMESTAMP
            WHERE round_id = ? AND status IN ({_in_list((RoundStatus.SETTING_THEME, RoundStatus.SUBMITTING))})
        """, (theme, RoundStatus.SUBMITTING.value, round_id)).rowcount
        return updated > 0

def update_round_playlist_db(round_id: int, playlist_id: str) -> None:
    """Saves the generated YouTube playlist ID to the round."""
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("UPDATE listen_rounds SET playlist_id = ? WHERE round_id = ?", (playlist_id, round_id))

def update_round_status_message_db(round_id: int, message_id: int) -> None:
    """Saves the message ID of the live submissions tracker for the round."""
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("UPDATE listen_rounds SET status_message_id = ? WHERE round_id = ?", (message_id, round_id))

def update_round_ruleset_message_db(round_id: int, message_id: int) -> None:
    """Saves the message ID of the host's ruleset post."""
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("UPDATE listen_rounds SET ruleset_message_id = ? WHERE round_id = ?", (message_id, round_id))

def close_round_db(round_id: int) -> bool:
    """Moves a round from `submitting` to `ranking`. Returns False if it wasn't accepting submissions."""
    with db_connection(Database.LISTEN_GAME) as conn:
        return _move_round(conn.cursor(), round_id, RoundStatus.RANKING, (RoundStatus.SUBMITTING,))

def is_round_complete_db(game_id: int, round_id: int) -> bool:
    """Checks if all non-host players have submitted their songs."""
    with db_connection(Database.LISTEN_GAME) as conn:
        total_players = conn.execute("SELECT COUNT(*) FROM listen_players WHERE game_id = ?", (game_id,)).fetchone()[0]
        total_submissions = conn.execute(
            "SELECT COUNT(*) FROM listen_submissions WHERE round_id = ?", (round_id,)
        ).fetchone()[0]

        # Everyone except the host needs to submit
        return total_submissions >= (total_players - 1)

def get_expired_rounds_db() -> list[Round]:
    """Fetches rounds that are still accepting submissions but have passed their deadline."""
    with db_connection(Database.LISTEN_GAME, row_factory=True) as conn:
        # Find rounds in 'submitting' state where max_round_days is set and exceeded
        rows = conn.execute("""
            SELECT r.*, g.max_round_days
            FROM listen_rounds r
            JOIN listen_games g ON r.game_id = g.game_id
            WHERE r.status = ? AND g.max_round_days IS NOT NULL
        """, (RoundStatus.SUBMITTING.value,)).fetchall()

        now = datetime.now(timezone.utc)
        return [
            Round.from_row(row) for row in rows
            if now >= parse_db_timestamp(row['started_at']) + timedelta(days=row['max_round_days'])
        ]

def get_missing_players_for_reminders_db() -> list[PendingPlayer]:
    """Fetches players who haven't submitted, along with round timing info."""
    with db_connection(Database.LISTEN_GAME, row_factory=True) as conn:
        # Joins players to the active round, checking who DOES NOT have a submission
        rows = conn.execute("""
            SELECT
                p.user_id, p.game_id, p.last_reminded_at,
                r.round_id, r.started_at, r.ruleset_message_id,
                g.max_round_days
            FROM listen_rounds r
            JOIN listen_games g ON r.game_id = g.game_id
            JOIN listen_players p ON g.game_id = p.game_id
            LEFT JOIN listen_submissions s
                ON r.round_id = s.round_id AND p.user_id = s.user_id
            WHERE r.status = ?
              AND s.user_id IS NULL       -- No submission found
              AND p.user_id != r.host_id  -- Host doesn't submit
        """, (RoundStatus.SUBMITTING.value,)).fetchall()
        return [PendingPlayer(**_row_to_fields(PendingPlayer, row)) for row in rows]

def update_last_reminded_db(game_id: int, user_id: int) -> None:
    """Updates the last_reminded_at timestamp for a player."""
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("""
            UPDATE listen_players SET last_reminded_at = CURRENT_TIMESTAMP
            WHERE game_id = ? AND user_id = ?
        """, (game_id, user_id))


# ---------------------------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------------------------

def get_round_submissions_db(round_id: int) -> list[Submission]:
    """Fetches all submissions for a given round."""
    with db_connection(Database.LISTEN_GAME, row_factory=True) as conn:
        rows = conn.execute("SELECT * FROM listen_submissions WHERE round_id = ?", (round_id,))
        return [Submission.from_row(row) for row in rows]

def get_user_submission_db(round_id: int, user_id: int) -> Submission | None:
    """Fetches a specific user's submission for a round."""
    with db_connection(Database.LISTEN_GAME, row_factory=True) as conn:
        row = conn.execute(
            "SELECT * FROM listen_submissions WHERE round_id = ? AND user_id = ?", (round_id, user_id)
        ).fetchone()
        return Submission.from_row(row) if row else None

def upsert_submission_db(round_id: int, user_id: int, video_id: str, raw_title: str) -> None:
    """Inserts a new submission or overwrites an existing one."""
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("""
            INSERT INTO listen_submissions (round_id, user_id, video_id, raw_title)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(round_id, user_id) DO UPDATE SET
                video_id = excluded.video_id,
                raw_title = excluded.raw_title,
                submitted_at = CURRENT_TIMESTAMP
        """, (round_id, user_id, video_id, raw_title))

def delete_submission_db(round_id: int, user_id: int) -> bool:
    """Removes a user's submission from the specified round. Returns False if they had none."""
    with db_connection(Database.LISTEN_GAME) as conn:
        removed = conn.execute(
            "DELETE FROM listen_submissions WHERE round_id = ? AND user_id = ?", (round_id, user_id)
        ).rowcount
        return removed > 0

def is_video_claimed_by_other_db(round_id: int, user_id: int, video_id: str) -> bool:
    """Checks if another player has already submitted this exact video ID in the round."""
    with db_connection(Database.LISTEN_GAME) as conn:
        row = conn.execute("""
            SELECT 1 FROM listen_submissions
            WHERE round_id = ? AND video_id = ? AND user_id != ?
            LIMIT 1
        """, (round_id, video_id, user_id)).fetchone()
        return row is not None


# ---------------------------------------------------------------------------------------------
# Ranking, reveal and moving on
# ---------------------------------------------------------------------------------------------

def save_ranking_pick_db(round_id: int, user_id: int, rank: int, commentary: str) -> None:
    """
    Saves one song the listener has ranked, before they confirm, so that a restart in the middle of
    ranking doesn't lose their work. Picking a song again replaces its earlier pick.
    """
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO listen_round_rankings (round_id, user_id, rank, commentary)
            VALUES (?, ?, ?, ?)
        """, (round_id, user_id, rank, commentary))

def get_ranking_picks_db(round_id: int) -> list[RankingPick]:
    """The songs the listener has ranked so far, in the order they picked them (last place first)."""
    with db_connection(Database.LISTEN_GAME) as conn:
        rows = conn.execute("""
            SELECT user_id, rank, commentary FROM listen_round_rankings
            WHERE round_id = ? ORDER BY rank DESC
        """, (round_id,))
        return [RankingPick(user_id=row[0], rank=row[1], commentary=row[2]) for row in rows]

def clear_ranking_picks_db(round_id: int) -> None:
    """Throws away the listener's unconfirmed picks, so they can start again."""
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("DELETE FROM listen_round_rankings WHERE round_id = ?", (round_id,))

def save_round_results_db(game_id: int, round_id: int, results: list[RoundResult]) -> SaveResult:
    """
    Saves rankings/commentary, applies points to player scores, and moves the round from
    `ranking` to `revealing`, all in one transaction. Because the status change is part of the
    transaction, the points can only ever be applied once per round.
    """
    with db_connection(Database.LISTEN_GAME) as conn:
        cursor = conn.cursor()

        if not _move_round(cursor, round_id, RoundStatus.REVEALING, (RoundStatus.RANKING,),
                           extra_assignments=", reveal_step = 0"):
            return SaveResult.NOT_IN_RANKING

        for res in results:
            # Update the submission row with the rank and commentary
            cursor.execute("""
                UPDATE listen_submissions
                SET rank = ?, points_awarded = ?, commentary = ?
                WHERE round_id = ? AND user_id = ?
            """, (res.rank, res.points, res.commentary, round_id, res.user_id))

            # Add the earned points to the player's total score
            cursor.execute("""
                UPDATE listen_players SET score = score + ?
                WHERE game_id = ? AND user_id = ?
            """, (res.points, game_id, res.user_id))

        # The picks have been confirmed, so the saved progress isn't needed any more
        cursor.execute("DELETE FROM listen_round_rankings WHERE round_id = ?", (round_id,))
        return SaveResult.SAVED

def get_revealing_round_ids_db() -> list[int]:
    """Fetches the IDs of rounds whose results are saved but whose reveal has not finished."""
    with db_connection(Database.LISTEN_GAME) as conn:
        rows = conn.execute("SELECT round_id FROM listen_rounds WHERE status = ? ORDER BY round_id",
                            (RoundStatus.REVEALING.value,))
        return [row[0] for row in rows]

def get_round_db(round_id: int) -> Round | None:
    """Fetches one round by its ID."""
    with db_connection(Database.LISTEN_GAME, row_factory=True) as conn:
        row = conn.execute("SELECT * FROM listen_rounds WHERE round_id = ?", (round_id,)).fetchone()
        return Round.from_row(row) if row else None

def set_reveal_step_db(round_id: int, step: int) -> None:
    """Records how many reveal messages have been posted so an interrupted reveal can resume."""
    with db_connection(Database.LISTEN_GAME) as conn:
        conn.execute("UPDATE listen_rounds SET reveal_step = ? WHERE round_id = ?", (step, round_id))

def get_round_results_db(round_id: int) -> list[Submission]:
    """Fetches the saved rankings for a round, best rank first."""
    with db_connection(Database.LISTEN_GAME, row_factory=True) as conn:
        rows = conn.execute("""
            SELECT * FROM listen_submissions
            WHERE round_id = ? AND rank IS NOT NULL
            ORDER BY rank ASC
        """, (round_id,))
        return [Submission.from_row(row) for row in rows]

def get_next_host_id_db(game_id: int, round_id: int) -> int | None:
    """Returns the next round's host without changing anything, or None if this is the last turn."""
    with db_connection(Database.LISTEN_GAME) as conn:
        return _find_next_host_id(conn.cursor(), game_id, round_id)

def advance_game_turn_db(game_id: int, round_id: int) -> bool:
    """
    Marks a revealed round completed and creates the next round, or finishes the game after the
    last turn. Safe to call again after it succeeded. Returns True if the round is completed.
    """
    with db_connection(Database.LISTEN_GAME) as conn:
        cursor = conn.cursor()

        if not _move_round(cursor, round_id, RoundStatus.COMPLETED, (RoundStatus.REVEALING,)):
            row = cursor.execute("SELECT status FROM listen_rounds WHERE round_id = ?", (round_id,)).fetchone()
            return bool(row) and row[0] == RoundStatus.COMPLETED

        next_host_id = _find_next_host_id(cursor, game_id, round_id)
        if next_host_id:
            _start_round(cursor, game_id, next_host_id)
        else:
            _move_game(cursor, game_id, GameStatus.FINISHED, (GameStatus.PLAYING,))
        return True

def skip_game_turn_db(game_id: int, round_id: int) -> int | None:
    """
    Marks the current round as skipped and moves on to the next player's turn.

    Returns the next host's user ID, or None if that was the last turn and the game has ended.
    Raises InvalidStateError if the round can no longer be skipped (its results are already being
    revealed, or it is finished).
    """
    with db_connection(Database.LISTEN_GAME) as conn:
        cursor = conn.cursor()

        if not _move_round(cursor, round_id, RoundStatus.SKIPPED, SKIPPABLE_ROUND_STATUSES):
            raise InvalidStateError(f"Round {round_id} can't be skipped in its current status")

        next_host_id = _find_next_host_id(cursor, game_id, round_id)
        if next_host_id:
            _start_round(cursor, game_id, next_host_id)
        else:
            _move_game(cursor, game_id, GameStatus.FINISHED, (GameStatus.PLAYING,))
        return next_host_id
