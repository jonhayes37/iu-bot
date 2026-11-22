"""
Reads the list files IU exports, `/export-lists` (`<event_id>_stats.txt`) and
`/export-end-of-year-nominations` (`top_25_<year>.txt`). Both look like this, with a blank line
between lists:

    --- username ---
    1. Artist // Song
    2. Artist // Song
"""

import re
from dataclasses import dataclass
from pathlib import Path

HEADER = re.compile(r"^---\s*(?P<user>.*?)\s*---$")
PICK = re.compile(r"^(?P<rank>\d+)[.)]\s*(?P<text>.*)$")
# IU turns "Artist - Song" and "Artist / Song" into "Artist // Song" when the list is submitted, so
# the others only matter for lists typed before IU collected them (the WAYLT spreadsheet)
SEPARATORS = (
    re.compile(r"\s*/{2,}\s*"),  # Artist // Song (also "//" and "///")
    re.compile(r"\s*/\.\s*"),  # Artist /. Song (typo)
    re.compile(r"\s+-\s*|\s*-\s+"),  # Artist - Song
)


class ListFileError(ValueError):
    """The file isn't laid out like IU's export. The message lists every problem found."""


@dataclass(frozen=True)
class Pick:
    """One line of a list."""
    rank: int
    text: str  # the line without its number
    artist: str | None  # None when the line has no "//" (IU accepts those rather than reject the list)
    song: str


@dataclass(frozen=True)
class Submission:
    """One member's list."""
    user: str
    picks: tuple[Pick, ...]


def split_pick(text: str) -> tuple[str, str] | None:
    """(artist, song) for one pick, or None if it has no artist/song separator."""
    for separator in SEPARATORS:
        parts = separator.split(text, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return parts[0].strip(), parts[1].strip()
    return None


def make_pick(rank: int, text: str) -> Pick:
    text = text.strip().strip("\"'").strip()
    split = split_pick(text)
    return Pick(rank, text, *split) if split else Pick(rank, text, None, text)


def load_lists(path: str | Path, expected_count: int | None = None) -> list[Submission]:
    """
    Every list in the file, in file order. Raises ListFileError, naming each problem, when a pick comes
    before any header, a member appears twice, the numbering isn't 1, 2, 3, ..., a list doesn't have
    expected_count picks, or a line is neither a header nor a numbered pick. Members whose list is empty
    are left out.
    """
    problems = []
    lists: dict[str, list[Pick]] = {}
    user = None
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        header = HEADER.match(line)
        pick = PICK.match(line)
        if header:
            user = header["user"]
            if user in lists:
                problems.append(f"line {number}: {user} has a second list")
            lists[user] = []
        elif pick and user is None:
            problems.append(f"line {number}: a pick before the first '--- username ---' line")
        elif pick:
            lists[user].append(make_pick(int(pick["rank"]), pick["text"]))
        else:
            problems.append(f"line {number}: expected '--- username ---' or a numbered pick, found {line!r}")

    for name, picks in lists.items():
        if [p.rank for p in picks] != list(range(1, len(picks) + 1)):
            problems.append(f"{name}: the picks aren't numbered 1, 2, 3, ...")
        if picks and expected_count is not None and len(picks) != expected_count:
            problems.append(f"{name}: {len(picks)} picks, expected {expected_count}")
    if problems:
        raise ListFileError(f"{path}:\n  " + "\n  ".join(problems))
    return [Submission(name, tuple(picks)) for name, picks in lists.items() if picks]
