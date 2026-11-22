"""The report sections every list video shares, so they read the same in every report."""

from stats.common.report import Report
from stats.common.tally import Tallies, competition_ranks


def who(names: list[str]) -> str:
    """Names in the order given, each once, with (xN) for anyone listed several times."""
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(name if n == 1 else f"{name} (x{n})" for name, n in counts.items())


def most_picked_songs(report: Report, tallies: Tallies, scored: bool, note: str = ""):
    """Songs on more than one list. `scored` adds a points column."""
    songs = sorted((t for t in tallies.songs.values() if t.picks > 1),
                   key=lambda t: (-t.picks, -t.points, tallies.song_name(t.key).casefold()))
    report.section("Most picked songs", f"Songs picked more than once{note}.")
    rows = [[rank, tallies.song_name(t.key), t.picks, *([t.points] if scored else []), who(t.pickers)]
            for rank, t in competition_ranks(songs, lambda t: t.picks)]
    report.table(["#", "Song", "Picks", *(["Points"] if scored else []), "Picked by"], rows)


def most_picked_artists(report: Report, tallies: Tallies):
    artists = sorted((t for t in tallies.artists.values() if t.picks > 1),
                     key=lambda t: (-t.picks, -len(set(t.pickers)), tallies.artist_name(t.key).casefold()))
    total = sum(t.picks for t in tallies.songs.values())
    report.section("Most picked artists", "Artists picked more than once.")
    report.table(["#", "Artist", "Picks", "Members", "Songs", "Share"],
                 [[rank, tallies.artist_name(t.key), t.picks, len(set(t.pickers)), len(t.songs),
                   f"{t.picks / total:.1%}"]
                  for rank, t in competition_ranks(artists, lambda t: t.picks)])


def most_songs_per_artist(report: Report, tallies: Tallies):
    artists = sorted((t for t in tallies.artists.values() if len(t.songs) > 1),
                     key=lambda t: (-len(t.songs), tallies.artist_name(t.key).casefold()))
    report.section("Most different songs by one artist")
    report.table(["#", "Artist", "Songs", "Titles"],
                 [[rank, tallies.artist_name(t.key), len(t.songs),
                   ", ".join(sorted((tallies.title(s) for s in t.songs), key=str.casefold))]
                  for rank, t in competition_ranks(artists, lambda t: len(t.songs))])


def data_notes(report: Report, tallies: Tallies, *extra: str):
    """Picks with no artist, spellings counted as one, and anything else the report needs to flag."""
    notes = [f"No '//' between artist and song, so counted as a song with no artist: {user} #{pick.rank} "
             f"{pick.text!r}" for user, pick in tallies.unsplit]
    notes += [f"Counted as one: {' / '.join(spellings)}" for spellings in tallies.merged_spellings()]
    notes += extra
    report.section("Data notes", *(f"- {note}" for note in notes or ["Nothing to note."]))
