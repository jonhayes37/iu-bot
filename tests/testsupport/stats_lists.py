"""Building list files like IU's exports, and reading reports back, for the stats/ tests."""

import re


def export(*lists: tuple[str, list[str]]) -> str:
    """The text /export-lists writes for these (member, picks) lists."""
    return "".join(f"--- {user} ---\n" + "".join(f"{i}. {pick}\n" for i, pick in enumerate(picks, 1)) + "\n"
                   for user, picks in lists)


def table_rows(text: str) -> list[list[str]]:
    """Every line of a report split into its cells (columns are two or more spaces apart)."""
    return [re.split(r"\s{2,}", line.strip()) for line in text.splitlines() if line.strip()]
