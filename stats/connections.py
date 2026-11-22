"""
Taste connections: how everyone's lists overlap, and who connects to whom.

    uv run python -m stats.connections top_100 stats/data/top_100/top_25_2025.txt

Takes the same formats and files as stats.ranked_lists (built for the end of year Top 25 lists, but
any ranked list file works). Saves four charts and a report in stats/output/:

- <file>_taste_network.png: members joined by how many songs they share, in taste groups;
- <file>_shared_songs_map.png: members around a ring and the songs several of them picked between them;
- <file>_overlap_matrix.png: the number of shared songs for every pair;
- <file>_consensus_target.png: how close each member's ranked picks came to the community's Top 15/25.

The community Top N is ranked as in stats.ranked_lists, ties included: `--seed N` repeats a draw there.
"""

import argparse
import random
import sys
from dataclasses import dataclass
from pathlib import Path

from stats.common.network import Connections, bridging_songs, connect, group_favourites
from stats.common.network_charts import (GROUP_NAMES, MIN_EDGE, MIN_PICKERS_ON_MAP, consensus_target,
                                         overlap_matrix, shared_songs_map, taste_network)
from stats.common.parsing import ListFileError, load_lists
from stats.common.report import OUTPUT_DIR, Report, write_report
from stats.common.sections import data_notes
from stats.common.similarity import shared_by_position
from stats.common.tally import Tallies, competition_ranks, rank_by_points, song_of, standing
from stats.ranked_lists import FORMATS, year_of

STRONGEST_PAIRS = 10
FAVOURITES_PER_GROUP = 5


@dataclass(frozen=True)
class Alignment:
    """How close one member's ranked picks came to the community's Top N."""
    member: str
    shared: int  # of their ranked picks, how many made the community Top N
    by_position: float  # the same, weighted by how near they ranked each to where the community did (%)


def build_report(fmt_name: str, path: Path, out_dir: Path, seed: int = 1) -> Report:
    fmt = FORMATS[fmt_name]
    submissions = load_lists(path, expected_count=fmt.ranked + fmt.honourable)
    tallies = Tallies(submissions, ranked=fmt.ranked)
    connections = connect({s.user: [song_of(p) for p in s.picks] for s in submissions})
    placings = rank_by_points(tallies.songs.values(), random.Random(seed))
    community = [placing.tally.key for placing in placings[:fmt.ranked]]
    alignments = [Alignment(s.user, len({song_of(p) for p in s.picks[:fmt.ranked]} & set(community)),
                            shared_by_position([song_of(p) for p in s.picks[:fmt.ranked]], community))
                  for s in submissions]
    cutoff_drawn = len(placings) > fmt.ranked and standing(placings[fmt.ranked - 1].tally) == \
        standing(placings[fmt.ranked].tally)
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
    _alignment(report, connections, alignments, fmt.ranked)
    _charts(report, connections, tallies, video, out_dir / path.stem, alignments, fmt.ranked)
    data_notes(report, tallies, *([f"The last places of the community Top {fmt.ranked} were tied and decided by the "
                                   f"random draw (seed {seed}; add --seed {seed} to repeat it)."]
                                  if cutoff_drawn else []))
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


def _alignment(report: Report, connections: Connections, alignments: list[Alignment], top_n: int):
    ordered = sorted(alignments, key=lambda a: (-a.shared, -a.by_position, a.member.casefold()))
    report.section(f"Closest to the community Top {top_n}",
                   f"Shared: how many of each member's {top_n} ranked picks made the community Top {top_n}. By "
                   "position: the same, counting each song less the further their placing was from the community's.")
    report.table(["#", "Member", "Group", "Shared", "By position"],
                 [[rank, a.member, _group_label(connections, a.member), a.shared, f"{a.by_position:.0f}%"]
                  for rank, a in competition_ranks(ordered, lambda a: a.shared)])


def _charts(report: Report, connections: Connections, tallies: Tallies, video: str, stem: Path,
            alignments: list[Alignment], top_n: int):
    report.section("Charts")
    results = [
        taste_network(connections, title=f"Nearest Neighbours - {video}",
                      path=stem.with_name(f"{stem.name}_taste_network.png")),
        shared_songs_map(connections, tallies.song_name, title=f"Song Connections - {video}",
                         path=stem.with_name(f"{stem.name}_shared_songs_map.png")),
        consensus_target(connections, {a.member: a.shared for a in alignments}, top_n,
                         title=f"Closest to the Community - {video}",
                         path=stem.with_name(f"{stem.name}_consensus_target.png")),
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
    parser.add_argument("--seed", type=int, help="repeat an earlier random draw for ties at the Top N cutoff")
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1, 1_000_000)
    try:
        report = build_report(args.format, args.path, args.out_dir, seed)
    except (ListFileError, FileNotFoundError) as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    write_report(report, f"{args.path.stem}_connections_report", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
