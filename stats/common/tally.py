"""Counting picks, points and #1s for every song and artist, and ranking them."""

import random
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from stats.common.normalize import Names, artist_key, display_artist, song_key
from stats.common.parsing import Pick, Submission

# A song is its artist's key and its title's key; the artist key is None for a pick with no "//"
SongKey = tuple[str | None, str]


@dataclass
class Tally:
    """One song's (or one artist's) picks across every list."""
    key: SongKey | str
    points: int = 0
    picks: int = 0
    firsts: int = 0
    pickers: list[str] = field(default_factory=list)  # one entry per pick, in file order
    firsts_by: list[str] = field(default_factory=list)
    songs: dict[SongKey, None] = field(default_factory=dict)  # an artist's songs, in the order first picked


def points_for(rank: int, ranked: int | None) -> int:
    """1st place is worth `ranked` points and last place 1; honourable mentions and unranked lists score 0."""
    return ranked - rank + 1 if ranked and rank <= ranked else 0


def song_of(pick: Pick) -> SongKey:
    return (artist_key(pick.artist) if pick.artist else None, song_key(pick.song))


class Tallies:
    """
    Every song and artist picked in a set of lists. `ranked` is how many picks per list score points
    (None for unranked lists like What Are You Listening To).
    """

    def __init__(self, submissions: Iterable[Submission], ranked: int | None = None):
        self.submissions = list(submissions)
        self.songs: dict[SongKey, Tally] = {}
        self.artists: dict[str, Tally] = {}
        self.artist_names = Names()
        self.song_names = Names()
        self.unsplit: list[tuple[str, Pick]] = []
        for submission in self.submissions:
            for pick in submission.picks:
                self._add(submission.user, pick, ranked)

    def _add(self, user: str, pick: Pick, ranked: int | None):
        key = song_of(pick)
        points = points_for(pick.rank, ranked)
        first = bool(ranked) and pick.rank == 1
        self.song_names.add(key, pick.song)
        tallies = [self.songs.setdefault(key, Tally(key))]
        if pick.artist is None:
            self.unsplit.append((user, pick))
        else:
            self.artist_names.add(key[0], display_artist(pick.artist))
            tallies.append(self.artists.setdefault(key[0], Tally(key[0])))
            tallies[1].songs[key] = None
        for tally in tallies:
            tally.points += points
            tally.picks += 1
            tally.pickers.append(user)
            if first:
                tally.firsts += 1
                tally.firsts_by.append(user)

    def song_name(self, key: SongKey) -> str:
        artist, _ = key
        title = self.song_names[key]
        return f"{self.artist_names[artist]} // {title}" if artist else title

    def artist_name(self, key: str) -> str:
        return self.artist_names[key]

    def title(self, key: SongKey) -> str:
        """Just the song's title."""
        return self.song_names[key]

    def merged_spellings(self) -> list[list[str]]:
        """Artists and songs typed more than one way (beyond capitals), each as its spellings."""
        songs = [[f"{self.artist_names[artist]} // {title}" if artist else title for title in titles]
                 for (artist, _), titles in self.song_names.merged()]
        return [spellings for _, spellings in self.artist_names.merged()] + songs


@dataclass(frozen=True)
class Placing:
    """A song's (or artist's) place in the points ranking."""
    place: int
    tally: Tally
    drawn: bool  # level with others on points, #1s and picks, so the random draw decided its place


def standing(tally: Tally) -> tuple[int, int, int]:
    """What decides the ranking: the most points, then the most #1 picks, then the most picks."""
    return tally.points, tally.firsts, tally.picks


def rank_by_points(tallies: Iterable[Tally], rng: random.Random) -> list[Placing]:
    """
    Best first. Tallies level on points, #1s and picks are put in a random order (the same order for the
    same rng seed) and marked drawn.
    """
    shuffled = sorted(tallies, key=lambda tally: repr(tally.key))  # so the draw doesn't depend on file order
    rng.shuffle(shuffled)
    ordered = sorted(shuffled, key=lambda tally: tuple(-n for n in standing(tally)))  # a stable sort
    level = Counter(standing(tally) for tally in ordered)
    return [Placing(place, tally, level[standing(tally)] > 1) for place, tally in enumerate(ordered, start=1)]


def competition_ranks[T](items: Sequence[T], value: Callable[[T], object]) -> list[tuple[int, T]]:
    """Ranks for items already sorted best first, shared when the value is equal (1, 2, 2, 4, ...)."""
    ranked = []
    for position, item in enumerate(items, start=1):
        shared = ranked and value(ranked[-1][1]) == value(item)
        ranked.append((ranked[-1][0] if shared else position, item))
    return ranked
