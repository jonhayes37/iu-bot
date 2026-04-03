"""String-related helper functions"""

def get_ordinal(n: int) -> str:
    """Returns the ordinal string for a number (e.g., 1 -> 1st, 2 -> 2nd)."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd', 'th', 'th', 'th', 'th', 'th', 'th'][n % 10]}"

def generate_leaderboard_text(leaderboard: list[dict]) -> str:
    """Formats the leaderboard data into a clean Discord message string."""
    board_text = "🏆 **Listen Game - Final Leaderboard** 🏆\n"
    board_text += "Thank you all for playing! Here are the final standings:\n\n"

    for i, player in enumerate(leaderboard, start=1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"
        board_text += f"{medal} **{get_ordinal(i)}:** <@{player['user_id']}> — {player['score']} pts\n"

    return board_text
