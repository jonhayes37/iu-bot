"""
All-time stats across every What Are You Listening To video.

    uv run python -m stats.waylt_all_time "What Are You Listening To Submissions - Picks.csv" \\
        stats/data/waylt/waylt_2026_*_stats.txt [--top 20]

Takes any mix of:
- the spreadsheet of the videos before IU collected the lists (.csv): one row per video, its label
  in the first column, and one column per member whose cell holds their picks, one per line, usually
  "Artist // Song" (sometimes "Artist - Song", numbered or written "Song // Artist");
- IU's `/export-lists` files (.txt), one per video, labelled by their event ID.

List the files oldest first: ties in the song ranking go to the song picked first.
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from stats.common.normalize import artist_key
from stats.common.parsing import PICK, ListFileError, Pick, Submission, load_lists, make_pick
from stats.common.report import OUTPUT_DIR, Report, write_report
from stats.common.sections import data_notes, who
from stats.common.tally import Tallies, competition_ranks, song_of


@dataclass
class Videos:
    """Every video's lists, oldest first, with what couldn't be read from the spreadsheet."""
    lists: list[tuple[str, Submission]]
    skipped: list[str]
    flipped: list[str]


def load_spreadsheet(path: Path) -> tuple[list[tuple[str, Submission]], list[str]]:
    """The spreadsheet's lists, and a note for every line without an artist/song separator (left out)."""
    lists, skipped = [], []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        users = [user.strip() for user in next(reader)[1:]]
        for row in reader:
            if not row or not row[0].strip():
                continue
            video = row[0].strip()
            for user, cell in zip(users, row[1:]):
                picks = []
                for line in filter(None, (raw.strip() for raw in cell.splitlines())):
                    numbered = PICK.match(line)
                    pick = make_pick(len(picks) + 1, numbered["text"] if numbered else line)
                    if pick.artist is None:
                        skipped.append(f"Skipped (no artist/song separator): {user}, {video}: {pick.text!r}")
                    else:
                        picks.append(pick)
                if picks:
                    lists.append((video, Submission(user, tuple(picks))))
    return lists, skipped


def load_videos(paths: list[Path]) -> Videos:
    lists, skipped = [], []
    for path in paths:
        if path.suffix.lower() == ".csv":
            rows, notes = load_spreadsheet(path)
            lists += rows
            skipped += notes
        else:
            video = path.stem.removesuffix("_stats")
            lists += [(video, submission) for submission in load_lists(path)]
    return Videos(lists, skipped, orient(lists))


def orient(lists: list[tuple[str, Submission]]) -> list[str]:
    """
    Flips lists written "Song // Artist" (in place) and returns a note for each. A pick looks reversed
    when its right side is more often seen as an artist than its left side; a list is flipped when most
    of its picks look reversed.
    """
    seen_as_artist = Counter(artist_key(p.artist) for _, s in lists for p in s.picks if p.artist)
    notes = []
    for index, (video, submission) in enumerate(lists):
        votes = Counter()
        for pick in (p for p in submission.picks if p.artist):
            left, right = seen_as_artist[artist_key(pick.artist)], seen_as_artist[artist_key(pick.song)]
            votes["flip"] += right > left
            votes["keep"] += left > right
        if votes["flip"] > votes["keep"]:
            flipped = tuple(_flip(p) for p in submission.picks)
            lists[index] = (video, replace(submission, picks=flipped))
            notes.append(f"Read as 'Song // Artist' and flipped: {submission.user}, {video}")
    return notes


def _flip(pick: Pick) -> Pick:
    return replace(pick, artist=pick.song, song=pick.artist) if pick.artist else pick


def build_report(paths: list[Path], top: int) -> Report:
    videos = load_videos(paths)
    tallies = Tallies(submission for _, submission in videos.lists)
    order = list(dict.fromkeys(video for video, _ in videos.lists))
    song_videos = defaultdict(list)
    for video, submission in videos.lists:
        for pick in submission.picks:
            song_videos[song_of(pick)].append(video)
    total = sum(t.picks for t in tallies.songs.values())
    members = {s.user for _, s in videos.lists}

    report = Report("What Are You Listening To: all-time picks",
                    f"Videos: {len(order)} ({order[0]} to {order[-1]})" if order else "Videos: 0",
                    f"{len(members)} members, {total} picks",
                    f"{len(tallies.songs)} different songs by {len(tallies.artists)} different artists")

    songs = sorted(tallies.songs.values(), key=lambda t: (-t.picks, -len(set(t.pickers)),
                                                          min(order.index(v) for v in song_videos[t.key])))
    report.section(f"Most picked songs (top {top})")
    report.table(["#", "Song", "Picks", "Members", "Videos", "Picked by"],
                 [[rank, tallies.song_name(t.key), t.picks, len(set(t.pickers)),
                   ", ".join(dict.fromkeys(song_videos[t.key])), who(t.pickers)]
                  for rank, t in competition_ranks(songs, lambda t: t.picks)[:top]])

    artists = sorted(tallies.artists.values(), key=lambda t: (-t.picks, -len(set(t.pickers))))
    report.section(f"Most picked artists (top {top})")
    report.table(["#", "Artist", "Picks", "Members", "Songs", "Share"],
                 [[rank, tallies.artist_name(t.key), t.picks, len(set(t.pickers)), len(t.songs),
                   f"{t.picks / total:.1%}"]
                  for rank, t in competition_ranks(artists, lambda t: t.picks)[:top]])

    widest = sorted(tallies.artists.values(), key=lambda t: (-len(set(t.pickers)), -t.picks))
    report.section(f"Artists picked by the most members (top {top})")
    report.table(["#", "Artist", "Members", "Picks"],
                 [[rank, tallies.artist_name(t.key), len(set(t.pickers)), t.picks]
                  for rank, t in competition_ranks(widest, lambda t: len(set(t.pickers)))[:top]])

    report.section("Each member's most picked artist")
    report.table(["Member", "Picks", "Favourite artist(s)"], _favourites(videos, tallies))

    data_notes(report, tallies, *videos.flipped, *videos.skipped)
    return report


def _favourites(videos: Videos, tallies: Tallies) -> list[list[object]]:
    by_member: dict[str, Counter] = defaultdict(Counter)
    for _, submission in videos.lists:
        for pick in submission.picks:
            if pick.artist:
                by_member[submission.user][artist_key(pick.artist)] += 1
    rows = []
    for member, artists in sorted(by_member.items(), key=lambda item: -item[1].total()):
        best = artists.most_common(1)[0][1]
        tied = [tallies.artist_name(a) for a, n in artists.most_common() if n == best]
        names = ", ".join(tied[:3]) + (f" +{len(tied) - 3} more" if len(tied) > 3 else "")
        rows.append([member, artists.total(), f"{names} ({best}{' each' if len(tied) > 1 else ''})"])
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", type=Path, nargs="+", help="the spreadsheet and/or export files, oldest first")
    parser.add_argument("--top", type=int, default=20, help="rows to show per ranking (default 20)")
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    try:
        report = build_report(args.paths, args.top)
    except (ListFileError, FileNotFoundError) as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    write_report(report, "waylt_all_time_report", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
