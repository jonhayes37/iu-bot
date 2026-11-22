"""
Stats for one What Are You Listening To video, from its `/export-lists` file:

    uv run python -m stats.waylt stats/data/waylt/waylt_2026_10_stats.txt

The picks aren't ranked, so there are no points: just the most picked songs and artists, and the
chains that link members' lists through a shared song (the order the video can follow). The report
is printed and saved in stats/output/.
"""

import argparse
import sys
from pathlib import Path

from stats.common.chains import find_chains
from stats.common.parsing import ListFileError, load_lists
from stats.common.report import OUTPUT_DIR, Report, write_report
from stats.common.sections import data_notes, most_picked_artists, most_picked_songs, most_songs_per_artist
from stats.common.tally import Tallies, song_of


def build_report(path: Path) -> Report:
    submissions = load_lists(path)
    tallies = Tallies(submissions)
    picks = sum(len(s.picks) for s in submissions)
    report = Report(f"What Are You Listening To ({path.stem.removesuffix('_stats')})",
                    f"Source: {path.name}",
                    f"{len(submissions)} lists, {picks} picks",
                    f"{len(tallies.songs)} different songs by {len(tallies.artists)} different artists")
    most_picked_songs(report, tallies, scored=False)
    most_picked_artists(report, tallies)
    most_songs_per_artist(report, tallies)
    timed_out = _chains(report, tallies)
    data_notes(report, tallies, *(["The chain search hit its time limit; these are the best chains found in "
                                   "time, maybe not the best possible."] if timed_out else []))
    return report


def _chains(report: Report, tallies: Tallies) -> bool:
    """Adds the chains section. Returns whether the search ran out of time."""
    result = find_chains({s.user: [song_of(p) for p in s.picks] for s in tallies.submissions})
    linked = sum(len(chain) for chain in result.chains)
    report.section("Chains", f"{linked} of {len(tallies.submissions)} members linked in {len(result.chains)} "
                             "chain(s), each sharing a song with the next.")
    if not result.chains:
        report.line("No two lists share a song.")
    for number, chain in enumerate(result.chains, start=1):
        report.line()
        report.line(f"Chain {number} ({len(chain)} members)")
        for member, song in chain:
            report.line(f"  {member}")
            if song is not None:
                report.line(f"    ↓ {tallies.song_name(song)}")
    return result.timed_out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="the file /export-lists made")
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    try:
        report = build_report(args.path)
    except (ListFileError, FileNotFoundError) as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    write_report(report, f"{args.path.stem}_report", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
