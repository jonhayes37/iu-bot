"""
Taste connections: how everyone's lists overlap, and who connects to whom.

    uv run python -m stats.connections top_100 stats/data/top_100/top_25_2025.txt

Takes the same formats and files as stats.ranked_lists (built for the end of year Top 25 lists, but
any ranked list file works). Saves three charts and a report in stats/output/:

- <file>_taste_network.png: members joined by how many songs they share, in taste groups;
- <file>_shared_songs_map.png: members around a ring and the songs several of them picked between them;
- <file>_overlap_matrix.png: the number of shared songs for every pair.
"""

import argparse
import sys
from pathlib import Path

from stats.common.network import Connections, bridging_songs, connect, group_favourites
from stats.common.network_charts import (GROUP_NAMES, MIN_EDGE, MIN_PICKERS_ON_MAP, overlap_matrix,
                                         shared_songs_map, taste_network)
from stats.common.parsing import ListFileError, load_lists
from stats.common.report import OUTPUT_DIR, Report, write_report
from stats.common.sections import data_notes
from stats.common.tally import Tallies, song_of
from stats.ranked_lists import FORMATS, year_of

STRONGEST_PAIRS = 10
FAVOURITES_PER_GROUP = 5


def build_report(fmt_name: str, path: Path, out_dir: Path) -> Report:
    fmt = FORMATS[fmt_name]
    submissions = load_lists(path, expected_count=fmt.ranked + fmt.honourable)
    tallies = Tallies(submissions, ranked=fmt.ranked)
    connections = connect({s.user: [song_of(p) for p in s.picks] for s in submissions})
    video = fmt.title.format(year=year_of(path))
    members = connections.members
    pairs = len(members) * (len(members) - 1) // 2
    total_shared = sum(len(songs) for songs in connections.shared.values())

    report = Report(f"Taste connections: {video}", f"Source: {path.name}",
                    f"{len(members)} members, {pairs} pairs: {len(connections.shared)} pairs share at least one "
                    f"song, {pairs - len(connections.shared)} share none",
                    f"On average a pair shares {total_shared / pairs if pairs else 0:.1f} songs")
    _groups(report, connections, tallies)
    _bridges(report, connections, tallies)
    _strongest(report, connections, tallies)
    _members(report, connections)
    _charts(report, connections, tallies, video, out_dir / path.stem)
    data_notes(report, tallies)
    return report


def _group_label(connections: Connections, member: str) -> str:
    group = connections.group_of(member)
    return "-" if group is None else f"{group + 1} ({GROUP_NAMES[group]})"


def _groups(report: Report, connections: Connections, tallies: Tallies):
    report.section("Taste groups", "Members who share more songs with each other than with everyone else, found by "
                                   "community detection. Each group's shared favourites are the songs most of its "
                                   "members picked.")
    for number, group in enumerate(connections.groups, start=1):
        report.line()
        report.line(f"Group {number} ({GROUP_NAMES[number - 1]}): {', '.join(group)}")
        for song, count in group_favourites(connections, group)[:FAVOURITES_PER_GROUP]:
            report.line(f"  {count} of {len(group)}: {tallies.song_name(song)}")
    if connections.ungrouped:
        report.line()
        report.line(f"In no group: {', '.join(connections.ungrouped)}")
    if not connections.groups:
        report.line("No groups: nobody shares a song.")


def _bridges(report: Report, connections: Connections, tallies: Tallies):
    rows = [[tallies.song_name(song), f"{groups} of {len(connections.groups)}", picks]
            for song, groups, picks in bridging_songs(connections)[:15]]
    report.section("Songs that bridge the groups", "Picked in more than one taste group.")
    report.table(["Song", "Groups", "Picks"], rows)


def _strongest(report: Report, connections: Connections, tallies: Tallies):
    pairs = sorted(connections.shared.items(), key=lambda item: (-len(item[1]), sorted(item[0])))
    report.section("Strongest connections", "The pairs with the most songs in common.")
    report.table(["Pair", "Shared", "Songs"],
                 [[" ↔ ".join(sorted(pair, key=connections.members.index)), len(songs),
                   ", ".join(tallies.song_name(s) for s in songs)] for pair, songs in pairs[:STRONGEST_PAIRS]])


def _members(report: Report, connections: Connections):
    rows = []
    for member in connections.members:
        partners = connections.partners(member)
        closest = ", ".join(f"{other} ({n})" for other, n in partners if n == partners[0][1]) if partners else "-"
        rows.append([member, _group_label(connections, member), len(partners), sum(n for _, n in partners), closest])
    rows.sort(key=lambda row: (-row[2], -row[3], row[0].casefold()))
    report.section("Each member's connections",
                   f"Connected: how many of the other {len(connections.members) - 1} members they share at least "
                   "one song with. Shared: their shared songs added up over every pair.")
    report.table(["Member", "Group", "Connected", "Shared", "Closest"], rows)


def _charts(report: Report, connections: Connections, tallies: Tallies, video: str, stem: Path):
    report.section("Charts")
    results = [
        taste_network(connections, title=f"Nearest Neighbours - {video}",
                      path=stem.with_name(f"{stem.name}_taste_network.png")),
        shared_songs_map(connections, tallies.song_name, title=f"Song Connections - {video}",
                         path=stem.with_name(f"{stem.name}_shared_songs_map.png")),
    ]
    matrix = overlap_matrix(connections, title=f"Overlap Matrix - {video}",
                            path=stem.with_name(f"{stem.name}_overlap_matrix.png"))
    for result in results:
        report.line(f"Saved {result.path}")
        for label in result.crowded:
            report.line(f"  Couldn't find a clear spot for the label {label!r}; it overlaps something.")
    report.line(f"Saved {matrix}")
    report.line(f"(The network draws pairs sharing {MIN_EDGE}+ songs; the map shows songs on {MIN_PICKERS_ON_MAP}+ "
                "lists.)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("format", choices=FORMATS)
    parser.add_argument("path", type=Path, help="the file IU exported")
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    try:
        report = build_report(args.format, args.path, args.out_dir)
    except (ListFileError, FileNotFoundError) as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    write_report(report, f"{args.path.stem}_connections_report", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
