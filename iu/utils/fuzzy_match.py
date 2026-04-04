"""Fuzzy matching logic used by the listen game"""

import logging
import re
from rapidfuzz import fuzz, process

logger = logging.getLogger('iu-bot')


def sanitize_title(youtube_title: str) -> str:
    """Strips brackets, parentheses, and forces lowercase for clean matching."""
    # Removes anything inside () or [] - e.g., "[MV]", "(Color Coded)"
    clean = re.sub(r'[\(\[].*?[\)\]]', '', youtube_title)
    # Remove special characters except alphanumeric and spaces
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', clean)
    # Collapse multiple spaces into one and lowercase
    return re.sub(r'\s+', ' ', clean).strip().lower()

def evaluate_submission(new_raw_title: str, existing_submissions_map: dict[str, str]) -> dict:
    """
    existing_submissions_map should be a dictionary of {clean_title: raw_title}.
    """
    if not existing_submissions_map:
        return {'action': 'ALLOW', 'score': 0, 'match': None}

    new_clean = sanitize_title(new_raw_title)

    # We pass the clean_title keys to RapidFuzz to do the actual math
    best_match = process.extractOne(
        new_clean,
        existing_submissions_map.keys(),
        scorer=fuzz.token_sort_ratio
    )

    if not best_match:
        return {'action': 'ALLOW', 'score': 0, 'match': None}

    match_string, score, _ = best_match
    score = round(score, 2)

    # Map the winning clean_title back to its human-readable raw_title
    original_matched_title = existing_submissions_map[match_string]
    logger.info("Match score between %s and %s: %s", new_raw_title, original_matched_title, score)

    if score >= 70:
        return {'action': 'BLOCK', 'score': score, 'match': original_matched_title}
    if score >= 50:
        return {'action': 'WARN', 'score': score, 'match': original_matched_title}
    else:
        return {'action': 'ALLOW', 'score': score, 'match': None}
