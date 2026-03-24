"""Database operations and math helpers for the tournament bracket feature."""

import os
import sqlite3
import logging
import math
import random
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

logger = logging.getLogger('iu-bot')

DB_PATH_TOURNAMENTS = os.getenv('DB_PATH_TOURNAMENTS')

def _get_perfect_seeding(num_entrants: int) -> List[int]:
    """
    Recursively generates standard bracket seeding order.
    For 8 entrants: [1, 8, 4, 5, 2, 7, 3, 6]
    """
    matches = [1, 2]
    for rounds in range(1, int(math.log2(num_entrants))):
        out = []
        sum_seeds = (2 ** (rounds + 1)) + 1
        for i in matches:
            out.append(i)
            out.append(sum_seeds - i)
        matches = out
    return matches

def create_tournament(name: str, entrants: List[str], days_per_round: int) -> Tuple[bool, str, str]:
    """
    Creates a tournament, entrants, and the linked match tree in one transaction.
    Returns: (Success, Tournament ID, Error Message)
    """
    num_entrants = len(entrants)
    total_rounds = int(math.log2(num_entrants))
    tournament_id = uuid.uuid4().hex[:8] # Clean, short ID

    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            cursor = conn.cursor()

            # 1. Create the parent tournament record
            cursor.execute("""
                INSERT INTO tournaments (tournament_id, name, days_per_round)
                VALUES (?, ?, ?)
            """, (tournament_id, name, days_per_round))

            # 2. Insert entrants and map their seeds to their new DB IDs
            seed_to_entrant_id = {}
            for i, entrant_name in enumerate(entrants):
                seed = i + 1
                cursor.execute("""
                    INSERT INTO tournament_entrants (tournament_id, name, seed)
                    VALUES (?, ?, ?)
                """, (tournament_id, entrant_name.strip(), seed))
                seed_to_entrant_id[seed] = cursor.lastrowid

            # 3. Generate the Matches (From Finals down to Round 1)
            match_dict = {} # Maps (round_num, position) to match_id
            seeding_array = _get_perfect_seeding(num_entrants)

            for round_num in range(total_rounds, 0, -1):
                num_matches = 2 ** (total_rounds - round_num)

                for pos in range(1, num_matches + 1):
                    # Link to the next round if it's not the final
                    next_match_id = None if round_num == total_rounds else \
                        match_dict[(round_num + 1, math.ceil(pos / 2))]

                    # If Round 1, populate the initial entrants based on perfect seeding
                    entrant_a_id = None
                    entrant_b_id = None
                    if round_num == 1:
                        seed_a = seeding_array[(pos - 1) * 2]
                        seed_b = seeding_array[(pos - 1) * 2 + 1]
                        entrant_a_id = seed_to_entrant_id[seed_a]
                        entrant_b_id = seed_to_entrant_id[seed_b]

                    cursor.execute("""
                        INSERT INTO tournament_matches
                        (tournament_id, round_num, match_position, entrant_a_id, entrant_b_id, next_match_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (tournament_id, round_num, pos, entrant_a_id, entrant_b_id, next_match_id))

                    match_dict[(round_num, pos)] = cursor.lastrowid

            # Context manager handles the commit automatically
            return True, tournament_id, ""

    except Exception as ex:
        logger.error("Failed to create tournament: %s", ex)
        return False, "", str(ex)

def get_bracket_render_data(tournament_id: str) -> dict | None:
    """
    Fetches the full tournament state and formats it dynamically for the Jinja template.
    Supports any power-of-2 entrant size (4, 8, 16, 32, 64, etc.).
    """
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get Tournament Name
            cursor.execute("SELECT name FROM tournaments WHERE tournament_id = ?", (tournament_id,))
            t_row = cursor.fetchone()
            if not t_row:
                return None

            # 2. Get all matches joined with their entrant data
            cursor.execute("""
                SELECT 
                    m.round_num, m.match_position,
                    e1.seed AS a_seed, e1.name AS a_name,
                    e2.seed AS b_seed, e2.name AS b_name,
                    w.name AS winner_name
                FROM tournament_matches m
                LEFT JOIN tournament_entrants e1 ON m.entrant_a_id = e1.entrant_id
                LEFT JOIN tournament_entrants e2 ON m.entrant_b_id = e2.entrant_id
                LEFT JOIN tournament_entrants w ON m.winner_id = w.entrant_id
                WHERE m.tournament_id = ?
                ORDER BY m.round_num ASC, m.match_position ASC
            """, (tournament_id,))

            matches = cursor.fetchall()
            if not matches:
                return None

            # Dynamically determine the total depth of the tree
            total_rounds = max(row["round_num"] for row in matches)

            # 3. Organize into a dynamic Context Dictionary
            context = {
                "tournament_title": t_row["name"],
                "total_rounds": total_rounds,
                "left_rounds": [[] for _ in range(total_rounds - 1)],
                "right_rounds": [[] for _ in range(total_rounds - 1)],
                "finals": None,
                "winner": "WINNER"
            }

            for row in matches:
                match_data = {
                    "a_seed": row["a_seed"] or "", "a_name": row["a_name"] or "",
                    "b_seed": row["b_seed"] or "", "b_name": row["b_name"] or ""
                }

                r = row["round_num"]
                pos = row["match_position"]

                if r == total_rounds:
                    context["finals"] = match_data
                    if row["winner_name"]:
                        context["winner"] = row["winner_name"]
                else:
                    # In round 'r', there are 2^(total_rounds - r) total matches.
                    # Exactly half belong to the left tree, half to the right tree.
                    half_matches = 2 ** (total_rounds - r - 1)

                    # 'r' is 1-indexed. The Python list is 0-indexed.
                    if pos <= half_matches:
                        context["left_rounds"][r - 1].append(match_data)
                    else:
                        context["right_rounds"][r - 1].append(match_data)

            return context

    except Exception as ex:
        logger.error("Failed to fetch bracket data for render: %s", ex)
        return None

def get_unpolled_matches(tournament_id: str, round_num: int) -> list[dict] | None:
    """
    Fetches matches in a specific round that have fully populated entrants but no poll message_id.
    """
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    m.match_id,
                    e1.name AS a_name,
                    e2.name AS b_name
                FROM tournament_matches m
                JOIN tournament_entrants e1 ON m.entrant_a_id = e1.entrant_id
                JOIN tournament_entrants e2 ON m.entrant_b_id = e2.entrant_id
                WHERE m.tournament_id = ? AND m.round_num = ? AND m.message_id IS NULL
                ORDER BY m.match_position ASC
            """, (tournament_id, round_num))

            return [dict(row) for row in cursor.fetchall()]

    except Exception as ex:
        logger.error("Failed to fetch unpolled matches: %s", ex)
        return None

def set_match_poll_data(match_id: int, message_id: int, end_time: datetime) -> bool:
    """
    Saves the Discord message ID and the exact expiration timestamp to the match record.
    """
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            cursor = conn.cursor()
            # Storing as an ISO-8601 string makes it incredibly easy to parse later
            cursor.execute("""
                UPDATE tournament_matches 
                SET message_id = ?, end_timestamp = ?
                WHERE match_id = ?
            """, (message_id, end_time.isoformat(), match_id))
            return True

    except Exception as ex:
        logger.error("Failed to set match poll data for match %s: %s", match_id, ex)
        return False

def get_expired_unresolved_matches() -> list[dict] | None:
    """Fetches matches where the poll has ended but no winner has been declared."""
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                SELECT match_id, tournament_id, round_num, match_position, message_id,
                       entrant_a_id, entrant_b_id
                FROM tournament_matches
                WHERE end_timestamp <= ? AND winner_id IS NULL AND message_id IS NOT NULL
            """, (now_iso,))

            return [dict(row) for row in cursor.fetchall()]
    except Exception as ex:
        logger.error("Failed to fetch expired matches: %s", ex)
        return None

def advance_winner(match_id: int, tournament_id: str, current_round: int, current_pos: int, winner_id: int) -> bool:
    """Marks the winner and slots them into the next round of the bracket."""
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            cursor = conn.cursor()

            # Mark the winner of the current match
            cursor.execute("""
                UPDATE tournament_matches 
                SET winner_id = ? 
                WHERE match_id = ?
            """, (winner_id, match_id))

            # Calculate the next slot in the binary tree
            next_round = current_round + 1
            next_pos = (current_pos + 1) // 2
            is_entrant_a = current_pos % 2 != 0

            # Update the next round's match
            if is_entrant_a:
                cursor.execute("""
                    UPDATE tournament_matches SET entrant_a_id = ?
                    WHERE tournament_id = ? AND round_num = ? AND match_position = ?
                """, (winner_id, tournament_id, next_round, next_pos))
            else:
                cursor.execute("""
                    UPDATE tournament_matches SET entrant_b_id = ?
                    WHERE tournament_id = ? AND round_num = ? AND match_position = ?
                """, (winner_id, tournament_id, next_round, next_pos))

            return True
    except Exception as ex:
        logger.error("Failed to advance winner for match %s: %s", match_id, ex)
        return False

def check_round_status(tournament_id: str) -> dict:
    """
    Analyzes the tournament to see which round is 'active' and if it's finished.
    Returns: { 'tournament_name': str, 'current_round': int, 'is_finished': bool, 'is_tournament_over': bool }
    """
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Find the lowest round number that isn't fully resolved
            # Joined with tournaments to grab the name in the same trip
            cursor.execute("""
                SELECT m.round_num, 
                       COUNT(m.match_id) as total_matches, 
                       COUNT(m.winner_id) as resolved_matches,
                       t.name
                FROM tournament_matches m
                JOIN tournaments t ON m.tournament_id = t.tournament_id
                WHERE m.tournament_id = ?
                GROUP BY m.round_num, t.name
                ORDER BY m.round_num ASC
            """, (tournament_id,))

            rounds = cursor.fetchall()

            # Safety check: if the tournament has no matches or doesn't exist
            if not rounds:
                return {
                    "tournament_name": "Unknown", 
                    "current_round": 0, 
                    "is_finished": False, 
                    "is_tournament_over": False
                }

            for r in rounds:
                if r['resolved_matches'] < r['total_matches']:
                    # This round is still in progress
                    return {
                        "tournament_name": r['name'],
                        "current_round": r['round_num'],
                        "is_finished": False,
                        "is_tournament_over": False
                    }

            # If we get here, all existing rounds are resolved.
            last_round = rounds[-1]
            return {
                "tournament_name": last_round['name'],
                "current_round": last_round['round_num'],
                "is_finished": True,
                "is_tournament_over": True
            }

    except Exception as ex:
        logger.error("Error checking round status: %s", ex)
        return {"tournament_name": "Unknown", "current_round": 0, "is_finished": False, "is_tournament_over": False}

def get_tournament_days(tournament_id: str) -> int:
    """
    Retrieves the configured days per round for a specific tournament.
    Defaults to 1 if something goes wrong to prevent the bot from stalling.
    """
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT days_per_round FROM tournaments WHERE tournament_id = ?", 
                (tournament_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else 1
    except Exception as ex:
        logger.error("Failed to fetch days_per_round for %s: %s", tournament_id, ex)
        return 1

def get_tournament_winner_name(tournament_id: str) -> str:
    """
    Fetches the name of the entrant who won the final match of the tournament.
    """
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            cursor = conn.cursor()
            # Select the winner_id from the highest round_num
            cursor.execute("""
                SELECT e.name 
                FROM tournament_matches m
                JOIN tournament_entrants e ON m.winner_id = e.entrant_id
                WHERE m.tournament_id = ?
                ORDER BY m.round_num DESC
                LIMIT 1
            """, (tournament_id,))
            row = cursor.fetchone()
            return row[0] if row else "Unknown Artist"
    except Exception as ex:
        logger.error("Failed to fetch winner name for %s: %s", tournament_id, ex)
        return "TBD"

def process_user_vote(message_id: int, user_id: int, answer_id: int) -> dict | None:
    """
    Saves a vote using the exact entrant_id. If this vote completes the round 
    for the user, it locks the reward ledger and returns tournament details.
    """
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Identify the match and its entrants
            cursor.execute("""
                SELECT match_id, tournament_id, round_num, entrant_a_id, entrant_b_id 
                FROM tournament_matches 
                WHERE message_id = ?
            """, (message_id,))
            match = cursor.fetchone()

            if not match:
                logger.error("No match found for message_id %s", message_id)
                return None

            t_id = match['tournament_id']
            r_num = match['round_num']
            m_id = match['match_id']

            # Discord polls are 1-indexed based on the order we added the answers
            choice_entrant_id = match['entrant_a_id'] if answer_id == 1 else match['entrant_b_id']

            # Save the vote using the composite key schema
            cursor.execute("""
                INSERT OR REPLACE INTO tournament_votes (match_id, user_id, choice_entrant_id)
                VALUES (?, ?, ?)
            """, (m_id, user_id, choice_entrant_id))

            # Check the ledger to see if they already claimed the reward
            cursor.execute("""
                SELECT 1 FROM tournament_rewards_ledger 
                WHERE tournament_id = ? AND round_num = ? AND user_id = ?
            """, (t_id, r_num, user_id))
            if cursor.fetchone():
                return None

            # Check total matches in Round vs. User's Votes in Round
            cursor.execute("""
                SELECT COUNT(*) FROM tournament_matches 
                WHERE tournament_id = ? AND round_num = ?
            """, (t_id, r_num))
            total_matches = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(DISTINCT v.match_id) 
                FROM tournament_votes v
                JOIN tournament_matches m ON v.match_id = m.match_id
                WHERE m.tournament_id = ? AND m.round_num = ? AND v.user_id = ?
            """, (t_id, r_num, user_id))
            user_votes = cursor.fetchone()[0]

            if user_votes >= total_matches:
                # Lock the reward in the ledger
                cursor.execute("""
                    INSERT INTO tournament_rewards_ledger (tournament_id, round_num, user_id)
                    VALUES (?, ?, ?)
                """, (t_id, r_num, user_id))

                # Fetch the tournament name for the Discord announcement
                cursor.execute("SELECT name FROM tournaments WHERE tournament_id = ?", (t_id,))
                t_name = cursor.fetchone()['name']

                return {"tournament_name": t_name, "round_num": r_num}

            return None

    except Exception as ex:
        logger.error("Failed to process user vote for %s: %s", user_id, ex)
        return None

def get_tournament_raffle_winner(tournament_id: str) -> dict | None:
    """
    Calculates total votes per user (1 vote = 1 ticket) and selects a winner.
    Returns the winning user_id, their ticket count, and the total pool size.
    """
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Count total votes per user across the entire tournament
            cursor.execute("""
                SELECT v.user_id, COUNT(v.match_id) as tickets
                FROM tournament_votes v
                JOIN tournament_matches m ON v.match_id = m.match_id
                WHERE m.tournament_id = ?
                GROUP BY v.user_id
            """, (tournament_id,))

            participants = cursor.fetchall()

            if not participants:
                return None # Nobody voted!

            # Extract populations and weights for Python's random selector
            user_ids = [row['user_id'] for row in participants]
            weights = [row['tickets'] for row in participants]

            # Select the winner heavily weighted by their participation
            winner_id = random.choices(user_ids, weights=weights, k=1)[0]

            # Grab the winner's ticket count for the announcement
            winner_tickets = next(row['tickets'] for row in participants if row['user_id'] == winner_id)
            total_pool = sum(weights)

            return {
                "user_id": winner_id, 
                "tickets": winner_tickets, 
                "total_pool": total_pool
            }

    except Exception as ex:
        logger.error("Failed to run raffle for %s: %s", tournament_id, ex)
        return None

def force_close_active_round(tournament_id: str) -> int:
    """
    Sets the end_timestamp of all active, unresolved matches to 'now'.
    Returns the number of matches affected.
    """
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            cursor = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()

            # Update only matches that have a live poll (message_id IS NOT NULL)
            # and haven't been resolved yet (winner_id IS NULL)
            cursor.execute("""
                UPDATE tournament_matches
                SET end_timestamp = ?
                WHERE tournament_id = ? AND winner_id IS NULL AND message_id IS NOT NULL
            """, (now_iso, tournament_id))

            return cursor.rowcount

    except Exception as ex:
        logger.error("Failed to force close round for %s: %s", tournament_id, ex)
        return 0

def get_active_tournament_id() -> str | None:
    """
    Retrieves the ID of the most recently created active tournament.
    """
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT tournament_id 
                FROM tournaments 
                WHERE status = 'active' 
                ORDER BY created_at DESC 
                LIMIT 1
            """)

            row = cursor.fetchone()
            return row[0] if row else None

    except Exception as ex:
        logger.error("Failed to fetch active tournament ID: %s", ex)
        return None

def set_tournament_completed(tournament_id: str) -> bool:
    """Marks a tournament as completed so the background task stops tracking it."""
    try:
        with sqlite3.connect(DB_PATH_TOURNAMENTS) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tournaments 
                SET status = 'completed' 
                WHERE tournament_id = ?
            """, (tournament_id,))
            return cursor.rowcount > 0
    except Exception as ex:
        logger.error("Failed to set tournament %s as completed: %s", tournament_id, ex)
        return False
