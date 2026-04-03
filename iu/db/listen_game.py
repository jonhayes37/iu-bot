"""Database logic for the listen game"""
import os
import sqlite3
import random
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger('iu-bot')

DB_PATH_LISTEN_GAME = os.getenv('DB_PATH_LISTEN_GAME')

def create_game_db(gm_id: int, max_round_days: int | None) -> int | None:
    """Creates a new game instance in the registration state."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()

            # Check if there is already an active game
            cursor.execute("SELECT game_id FROM listen_games WHERE status != 'finished'")
            if cursor.fetchone():
                return None

            cursor.execute("""
                INSERT INTO listen_games (gm_id, status, max_round_days)
                VALUES (?, 'registration', ?)
            """, (gm_id, max_round_days))

            return cursor.lastrowid
    except Exception as ex:
        logger.error("Error creating listen game: %s", ex)
        return None

def start_game_db(game_id: int) -> list[int] | None:
    """Transitions game, randomizes DB turn orders, and sets up Round 1."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()

            # Fetch current players who registered via the UI
            cursor.execute("SELECT user_id FROM listen_players WHERE game_id = ?", (game_id,))
            players = [row[0] for row in cursor.fetchall()]

            if len(players) < 3:
                return None

            random.shuffle(players)

            # Update status
            cursor.execute("UPDATE listen_games SET status = 'playing' WHERE game_id = ?", (game_id,))

            # Update turn orders natively in the DB
            for order, uid in enumerate(players):
                cursor.execute("""
                    UPDATE listen_players SET turn_order = ?
                    WHERE game_id = ? AND user_id = ?
                """, (order, game_id, uid))

            # Create Round 1
            first_host = players[0]
            cursor.execute("""
                INSERT INTO listen_rounds (game_id, host_id, status)
                VALUES (?, ?, 'setting_theme')
            """, (game_id, first_host))

            return players
    except Exception as ex:
        logger.error("Error starting listen game: %s", ex)
        return None

def get_game_by_status_db(status: str) -> dict | None:
    """Fetches a game record based on its current phase."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM listen_games WHERE status = ?", (status,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as ex:
        logger.error("Error fetching game by status '%s': %s", status, ex)
        return None

def register_player_db(game_id: int, user_id: int) -> bool:
    """Adds a player to a game. Returns True if added, False if they already joined."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            # Score and turn_order default to 0/NULL
            cursor.execute("""
                INSERT INTO listen_players (game_id, user_id, score)
                VALUES (?, ?, 0)
            """, (game_id, user_id))
            return True
    except sqlite3.IntegrityError:
        return False # Player already registered
    except Exception as ex:
        logger.error("Error registering player: %s", ex)
        return False

def unregister_player_db(game_id: int, user_id: int) -> bool:
    """Removes a player from a game during registration."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM listen_players WHERE game_id = ? AND user_id = ?", (game_id, user_id))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Error unregistering player: %s", ex)
        return False

def get_registered_players_db(game_id: int) -> list[int]:
    """Returns a list of user_ids registered for the game."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM listen_players WHERE game_id = ?", (game_id,))
            return [row[0] for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Error fetching players: %s", ex)
        return []

def get_current_round_db(game_id: int) -> dict | None:
    """Fetches the currently active round for a game."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM listen_rounds WHERE game_id = ? AND "
                "status != 'completed' ORDER BY round_id DESC LIMIT 1",
                (game_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as ex:
        logger.error("Error fetching current round: %s", ex)
        return None

def set_round_theme_db(round_id: int, theme: str) -> bool:
    """Saves the theme, starts the timer, and advances the state to submitting."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE listen_rounds 
                SET theme = ?, status = 'submitting', started_at = CURRENT_TIMESTAMP
                WHERE round_id = ?
            """, (theme, round_id))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Error setting round theme: %s", ex)
        return False

def get_round_submissions_db(round_id: int) -> list[dict]:
    """Fetches all successful submissions for a given round."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM listen_submissions WHERE round_id = ?", (round_id,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Error fetching submissions: %s", ex)
        return []

def get_user_submission_db(round_id: int, user_id: int) -> dict | None:
    """Fetches a specific user's submission for the current round."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM listen_submissions WHERE round_id = ? AND user_id = ?", (round_id, user_id))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as ex:
        logger.error("Error fetching user submission: %s", ex)
        return None

def upsert_submission_db(round_id: int, user_id: int, video_id: str, raw_title: str, clean_title: str) -> bool:
    """Inserts a new submission or overwrites an existing one."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO listen_submissions (round_id, user_id, video_id, raw_title, clean_title)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(round_id, user_id) DO UPDATE SET 
                    video_id = excluded.video_id, 
                    raw_title = excluded.raw_title,
                    clean_title = excluded.clean_title,
                    submitted_at = CURRENT_TIMESTAMP
            """, (round_id, user_id, video_id, raw_title, clean_title))
            return True
    except Exception as ex:
        logger.error("Error upserting submission: %s", ex)
        return False

def update_round_playlist_db(round_id: int, playlist_id: str) -> bool:
    """Saves the generated YouTube playlist ID to the round."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE listen_rounds SET playlist_id = ? WHERE round_id = ?", (playlist_id, round_id))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Error updating round playlist: %s", ex)
        return False

def is_round_complete_db(game_id: int, round_id: int) -> bool:
    """Checks if all non-host players have submitted their songs."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            # Get total players
            cursor.execute("SELECT COUNT(*) FROM listen_players WHERE game_id = ?", (game_id,))
            total_players = cursor.fetchone()[0]

            # Get total submissions
            cursor.execute("SELECT COUNT(*) FROM listen_submissions WHERE round_id = ?", (round_id,))
            total_submissions = cursor.fetchone()[0]

            # Everyone except the host needs to submit
            return total_submissions >= (total_players - 1)
    except Exception as ex:
        logger.error("Error checking round completion: %s", ex)
        return False

def get_missing_players_for_reminders_db() -> list[dict]:
    """Fetches players who haven't submitted, along with round timing info."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Joins players to the active round, checking who DOES NOT have a submission
            cursor.execute("""
                SELECT 
                    p.user_id, p.game_id, p.last_reminded_at,
                    r.round_id, r.started_at, 
                    g.max_round_days 
                FROM listen_rounds r
                JOIN listen_games g ON r.game_id = g.game_id
                JOIN listen_players p ON g.game_id = p.game_id
                LEFT JOIN listen_submissions s 
                    ON r.round_id = s.round_id AND p.user_id = s.user_id
                WHERE r.status = 'submitting' 
                  AND s.user_id IS NULL       -- No submission found
                  AND p.user_id != r.host_id  -- Host doesn't submit
            """)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Error fetching missing players for reminders: %s", ex)
        return []

def update_last_reminded_db(game_id: int, user_id: int) -> bool:
    """Updates the last_reminded_at timestamp for a player."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE listen_players 
                SET last_reminded_at = CURRENT_TIMESTAMP
                WHERE game_id = ? AND user_id = ?
            """, (game_id, user_id))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Error updating last reminded: %s", ex)
        return False

def get_expired_rounds_db() -> list[dict]:
    """Fetches rounds that are still accepting submissions but have passed their deadline."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Find rounds in 'submitting' state where max_round_days is set and exceeded
            cursor.execute("""
                SELECT 
                    r.round_id, r.game_id, r.host_id, r.playlist_id, 
                    r.started_at, g.max_round_days
                FROM listen_rounds r
                JOIN listen_games g ON r.game_id = g.game_id
                WHERE r.status = 'submitting' 
                  AND g.max_round_days IS NOT NULL
            """)

            expired_rounds = []
            now = datetime.now(timezone.utc)
            for row in cursor.fetchall():
                started_at = datetime.strptime(row['started_at'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                deadline = started_at + timedelta(days=row['max_round_days'])

                if now >= deadline:
                    expired_rounds.append(dict(row))

            return expired_rounds
    except Exception as ex:
        logger.error("Error fetching expired rounds: %s", ex)
        return []

def close_round_db(round_id: int) -> bool:
    """Transitions a round from 'submitting' to 'ranking'."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE listen_rounds 
                SET status = 'ranking'
                WHERE round_id = ?
            """, (round_id,))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Error closing round: %s", ex)
        return False

def save_round_results_db(game_id: int, round_id: int, results: list[dict]) -> bool:
    """Saves rankings/commentary and applies points to player scores in one transaction."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()

            for res in results:
                # Update the submission row with the rank and commentary
                cursor.execute("""
                    UPDATE listen_submissions 
                    SET rank = ?, points_awarded = ?, commentary = ?
                    WHERE round_id = ? AND user_id = ?
                """, (res['rank'], res['points'], res['commentary'], round_id, res['user_id']))

                # Add the earned points to the player's total score
                cursor.execute("""
                    UPDATE listen_players
                    SET score = score + ?
                    WHERE game_id = ? AND user_id = ?
                """, (res['points'], game_id, res['user_id']))

            return True
    except Exception as ex:
        logger.error("Error saving round results: %s", ex)
        return False

def advance_game_turn_db(game_id: int, round_id: int) -> int | None:
    """
    Marks current round completed, finds next host,
    and creates the next round. Returns new host_id or 
    None if game over.
    """

    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()

            # Close current round
            cursor.execute("UPDATE listen_rounds SET status = 'completed' WHERE round_id = ?", (round_id,))

            # Get current host's turn order
            cursor.execute("""
                SELECT p.turn_order 
                FROM listen_rounds r
                JOIN listen_players p ON r.host_id = p.user_id AND r.game_id = p.game_id
                WHERE r.round_id = ?
            """, (round_id,))
            current_turn_order = cursor.fetchone()[0]

            # Find the next player in the turn order
            cursor.execute("""
                SELECT user_id 
                FROM listen_players 
                WHERE game_id = ? AND turn_order > ? 
                ORDER BY turn_order ASC LIMIT 1
            """, (game_id, current_turn_order))

            next_player_row = cursor.fetchone()

            # If there is a next player, create the new round
            if next_player_row:
                next_host_id = next_player_row[0]
                cursor.execute("""
                    INSERT INTO listen_rounds (game_id, host_id, status)
                    VALUES (?, ?, 'setting_theme')
                """, (game_id, next_host_id))
                return next_host_id

            # If no next player, mark game as finished
            cursor.execute("UPDATE listen_games SET status = 'finished' WHERE game_id = ?", (game_id,))
            return None

    except Exception as ex:
        logger.error("Error advancing game turn: %s", ex)
        return None

def get_game_leaderboard_db(game_id: int) -> list[dict]:
    """Fetches the final scores for all players in a game, sorted highest to lowest."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT user_id, score
                FROM listen_players
                WHERE game_id = ?
                ORDER BY score DESC
            """, (game_id,))

            return [dict(row) for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Error fetching game leaderboard: %s", ex)
        return []

def delete_submission_db(round_id: int, user_id: int) -> bool:
    """Removes a user's submission from the specified round."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM listen_submissions WHERE round_id = ? AND user_id = ?",
                (round_id, user_id)
            )
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Error deleting submission: %s", ex)
        return False

def skip_game_turn_db(game_id: int, round_id: int) -> int | None:
    """Marks current round as skipped and advances the turn order to the next player.
    
    Returns the next host's user ID, or None if the game has ended.
    """
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()

            # Close current round as skipped
            cursor.execute("UPDATE listen_rounds SET status = 'skipped' WHERE round_id = ?", (round_id,))
            # Get current host's turn order
            cursor.execute("""
                SELECT p.turn_order 
                FROM listen_rounds r
                JOIN listen_players p ON r.host_id = p.user_id AND r.game_id = p.game_id
                WHERE r.round_id = ?
            """, (round_id,))
            current_turn_order = cursor.fetchone()[0]

            # Find the next player in the turn order
            cursor.execute("""
                SELECT user_id 
                FROM listen_players 
                WHERE game_id = ? AND turn_order > ? 
                ORDER BY turn_order ASC LIMIT 1
            """, (game_id, current_turn_order))

            next_player_row = cursor.fetchone()

            # If there is a next player, create the new round
            if next_player_row:
                next_host_id = next_player_row[0]
                cursor.execute("""
                    INSERT INTO listen_rounds (game_id, host_id, status)
                    VALUES (?, ?, 'setting_theme')
                """, (game_id, next_host_id))
                return next_host_id

            # If no next player, mark game as finished
            cursor.execute("UPDATE listen_games SET status = 'finished' WHERE game_id = ?", (game_id,))
            return None

    except Exception as ex:
        logger.error("Error skipping game turn: %s", ex)
        return None

def remove_player_from_game_db(game_id: int, user_id: int) -> bool:
    """Removes a player from the active game roster."""
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM listen_players WHERE game_id = ? AND user_id = ?",
                (game_id, user_id)
            )
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Error removing player: %s", ex)
        return False

def update_round_status_message_db(round_id: int, message_id: int) -> bool:
    """
    Saves the message ID of the live tracker for the round.

    Args:
        round_id (int): The ID of the current round.
        message_id (int): The Discord message ID to be stored.

    Returns:
        bool: True if the update was successful, False otherwise.
    """
    try:
        with sqlite3.connect(DB_PATH_LISTEN_GAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE listen_rounds
                SET status_message_id = ?
                WHERE round_id = ?
            """, (message_id, round_id))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Error updating status message ID: %s", ex)
        return False
