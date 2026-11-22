"""
Stats for the ranked list videos: the end of year Top 100 (from everyone's Top 25), the Top 15 So
Far (mid-year) and the All-Time Top 15.

    uv run python -m stats.ranked_lists top_100 stats/data/top_100/top_25_2025.txt
    uv run python -m stats.ranked_lists mid_year stats/data/mid_year/mid_year_2026_stats.txt
    uv run python -m stats.ranked_lists all_time stats/data/all_time/all_time_2026_stats.txt

The report is printed and saved in stats/output/, with the scatter chart for top_100 and mid_year.
Songs level on points are ranked by the most #1 picks, then the most picks, then a random draw; the
report names the seed, so `--seed N` repeats the same draw.
"""

import argparse
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from stats.common.parsing import ListFileError, load_lists
from stats.common.plot import Dot, scatter_chart
from stats.common.report import OUTPUT_DIR, Report, write_report
from stats.common.sections import data_notes, most_picked_artists, most_picked_songs, most_songs_per_artist
from stats.common.similarity import closest_lists, shared_by_position, shared_songs
from stats.common.tally import Placing, Tallies, competition_ranks, rank_by_points, song_of, standing


# With no cutoff (the all-time artist ranking), draws are noted in this many places
DRAWS_NOTED_WITHOUT_CUTOFF = 25


@dataclass(frozen=True)
class ListFormat:
    """What one kind of video's lists look like and which stats its report shows."""
    title: str  # {year} is filled in from the file name
    ranked: int  # picks per list that score points (1st = ranked points, last = 1)
    honourable: int = 0  # unscored picks after the ranked ones
    by_artist: bool = False  # rank artists by points instead of songs
    cutoff: int | None = None  # how many make the video
    ranking_rows: int | None = None  # rows of the points ranking to show (None: all)
    chart_title: str | None = None  # draw the scatter chart, with this title
    chart_labels: int = 0  # label the top this-many songs on the chart (as well as each column's extremes)
    compare_lists: bool = True  # the closest-lists and alignment sections


FORMATS = {
    "top_100": ListFormat("Top 25 Songs of {year}", ranked=25, cutoff=100,
                          chart_title="Top K-Pop Songs of {year}", chart_labels=20),
    "mid_year": ListFormat("Top 15 Songs of {year} So Far", ranked=15, honourable=1, cutoff=15, ranking_rows=25,
                           chart_title="Top K-Pop Songs of {year} So Far", chart_labels=15),
    # Few songs repeat on all-time lists, so the artists are what's ranked
    "all_time": ListFormat("All-Time Top 15 ({year})", ranked=15, by_artist=True, compare_lists=False),
}


def year_of(path: Path) -> str:
    match = re.search(r"20\d\d", path.name)
    return match.group() if match else ""


class RankedListReport:
    """Builds the report (and the chart) for one file of ranked lists."""

    def __init__(self, fmt: ListFormat, path: Path, seed: int):
        self.fmt, self.path, self.seed = fmt, path, seed
        self.year = year_of(path)
        submissions = load_lists(path, expected_count=fmt.ranked + fmt.honourable)
        self.tallies = Tallies(submissions, ranked=fmt.ranked)
        pool = self.tallies.artists if fmt.by_artist else self.tallies.songs
        self.placings = rank_by_points(pool.values(), random.Random(seed))
        self.name = self.tallies.artist_name if fmt.by_artist else self.tallies.song_name
        self.lists = {s.user: [song_of(p) for p in s.picks] for s in submissions}
        self.report = Report(fmt.title.format(year=self.year), *self._summary())

    def _summary(self) -> list[str]:
        fmt, lists = self.fmt, len(self.tallies.submissions)
        per_list = f"{fmt.ranked} ranked" + (f" + {fmt.honourable} honourable mention" if fmt.honourable else "")
        return [f"Source: {self.path.name}",
                f"{lists} lists, {lists * (fmt.ranked + fmt.honourable)} picks ({per_list} each), "
                f"{lists * fmt.ranked * (fmt.ranked + 1) // 2} points",
                f"{len(self.tallies.songs)} different songs by {len(self.tallies.artists)} different artists"]

    def build(self, out_dir: Path) -> Report:
        self._points_ranking()
        self._most_firsts()
        mention = " (honourable mentions count as picks)" if self.fmt.honourable else ""
        most_picked_songs(self.report, self.tallies, scored=True, note=mention)
        most_picked_artists(self.report, self.tallies)
        most_songs_per_artist(self.report, self.tallies)
        if self.fmt.compare_lists:
            self._closest_lists()
            self._alignment()
        if self.fmt.chart_title:
            self._chart(out_dir)
        self._data_notes()
        return self.report

    def _points_ranking(self):
        fmt, kind = self.fmt, "artists" if self.fmt.by_artist else "songs"
        rows_shown = fmt.ranking_rows or len(self.placings)
        title = f"Top {fmt.cutoff} {kind} by points" if fmt.cutoff else f"Top {kind} by points"
        self.report.section(title, "Ties are broken by the most #1 picks, then the most picks, then a random draw "
                                   "(marked *).")
        rows = []
        for placing in self.placings[:rows_shown]:
            tally = placing.tally
            row = [f"{placing.place}{'*' if placing.drawn else ''}", self.name(tally.key), tally.points,
                   tally.firsts, tally.picks]
            if fmt.by_artist:
                row.append(len(tally.songs))
            rows.append(row)
            if fmt.cutoff and placing.place == fmt.cutoff and rows_shown > fmt.cutoff:
                rows.append([f"---- {fmt.cutoff} make the video; the rest just missed out ----"])
        headers = ["#", "Artist" if fmt.by_artist else "Song", "Points", "#1s", "Picks"]
        self.report.table(headers + (["Songs"] if fmt.by_artist else []), rows)

    def _most_firsts(self):
        pool = self.tallies.artists if self.fmt.by_artist else self.tallies.songs
        firsts = sorted((t for t in pool.values() if t.firsts),
                        key=lambda t: (-t.firsts, -t.points, self.name(t.key).casefold()))
        self.report.section("Most #1 picks")
        if self.fmt.by_artist:
            number_ones = {s.user: song_of(s.picks[0]) for s in self.tallies.submissions}
            rows = [[rank, self.name(t.key), t.firsts,
                     ", ".join(f"{self.tallies.title(number_ones[u])} ({u})" for u in t.firsts_by)]
                    for rank, t in competition_ranks(firsts, lambda t: t.firsts)]
            self.report.table(["#", "Artist", "#1s", "Picked #1 (by)"], rows)
        else:
            rows = [[rank, self.name(t.key), t.firsts, ", ".join(t.firsts_by)]
                    for rank, t in competition_ranks(firsts, lambda t: t.firsts)]
            self.report.table(["#", "Song", "#1s", "Picked #1 by"], rows)

    def _closest_lists(self):
        for title, similarity, note in (
                ("Closest lists", shared_songs, "The share of each list's songs that are also on the other."),
                ("Closest lists, by position", shared_by_position,
                 "As above, but a shared song counts less the further apart the two lists placed it.")):
            self.report.section(title, note)
            # A member has fewer than 3 neighbours when there are fewer than 4 lists
            rows = [[member, *(f"{other} ({score:.0f}%)" for other, score in closest), *[""] * (3 - len(closest))]
                    for member, closest in closest_lists(self.lists, similarity).items()]
            self.report.table(["Member", "Closest", "2nd", "3rd"], rows)

    def _alignment(self):
        ranked = self.fmt.ranked
        overall = [placing.tally.key for placing in self.placings[:ranked]]
        scores = sorted(((member, shared_songs(songs[:ranked], overall), shared_by_position(songs[:ranked], overall))
                         for member, songs in self.lists.items()),
                        key=lambda row: (-row[2], -row[1], row[0].casefold()))
        self.report.section(f"Closest to the overall Top {ranked}",
                            f"How each member's {ranked} ranked picks compare with the community's top {ranked}.")
        self.report.table(["#", "Member", "Shared", "By position"],
                          [[rank, member, f"{simple:.0f}%", f"{positional:.0f}%"]
                           for rank, (member, simple, positional) in competition_ranks(scores, lambda row: row[2])])

    def _chart(self, out_dir: Path):
        fmt = self.fmt
        made = {p.tally.key for p in self.placings[:fmt.cutoff]}
        labelled = {p.tally.key for p in self.placings[:fmt.chart_labels]}
        columns: dict[int, list] = {}
        for tally in self.tallies.songs.values():
            if tally.picks > 1:
                columns.setdefault(tally.picks, []).append(tally)
        for tallies in columns.values():  # the highest and lowest scorer of each column of 2+ picks
            tallies.sort(key=lambda t: (t.points, self.tallies.song_name(t.key).casefold()))
            labelled |= {tallies[0].key, tallies[-1].key}

        dots = [Dot(t.picks, t.points, self.tallies.song_name(t.key).replace(" // ", " – ") if t.key in labelled
                    else None, t.key in made) for t in self.tallies.songs.values()]
        cutoff_points = self.placings[fmt.cutoff - 1].tally.points if len(self.placings) >= fmt.cutoff else None
        result = scatter_chart(dots, title=fmt.chart_title.format(year=self.year), cutoff_points=cutoff_points,
                               cutoff_label=f"Top {fmt.cutoff}", path=out_dir / f"{self.path.stem}_chart.png")
        self.report.section("Chart", f"Saved to {result.path}")
        for label in result.crowded:
            self.report.line(f"  Couldn't find a clear spot for the label {label!r}; it overlaps something.")

    def _data_notes(self):
        data_notes(self.report, self.tallies, *self._draw_notes())

    def _draw_notes(self) -> list[str]:
        groups: list[list[Placing]] = []  # runs of placings level on every count (they're next to each other)
        for placing in (p for p in self.placings if p.drawn):
            if groups and standing(groups[-1][-1].tally) == standing(placing.tally):
                groups[-1].append(placing)
            else:
                groups.append([placing])
        cutoff = self.fmt.cutoff
        # Only the places the video shows matter: the cutoff, or the top of an uncut ranking
        shown = cutoff or self.fmt.ranking_rows or DRAWS_NOTED_WITHOUT_CUTOFF
        groups = [group for group in groups if group[0].place <= shown]
        if not groups:
            return []
        notes = [f"Places in the top {shown} decided by the random draw (seed {self.seed}; add --seed {self.seed} "
                 "to repeat it): " + ", ".join(f"{g[0].place}-{g[-1].place}" for g in groups)]
        for group in groups:
            if cutoff and group[0].place <= cutoff < group[-1].place:
                made = [self.name(p.tally.key) for p in group if p.place <= cutoff]
                missed = [self.name(p.tally.key) for p in group if p.place > cutoff]
                notes.append(f"⚠️ The draw decided the Top {cutoff} cutoff: {', '.join(made)} made it; "
                             f"{', '.join(missed)} didn't (all level on points, #1s and picks).")
        return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("format", choices=FORMATS)
    parser.add_argument("path", type=Path, help="the file IU exported")
    parser.add_argument("--seed", type=int, help="repeat an earlier random draw for ties")
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1, 1_000_000)
    try:
        report = RankedListReport(FORMATS[args.format], args.path, seed).build(args.out_dir)
    except (ListFileError, FileNotFoundError) as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    write_report(report, f"{args.path.stem}_report", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
