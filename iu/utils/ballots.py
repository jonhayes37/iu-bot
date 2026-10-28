"""Counting the ranked end of year ballots: a 1st choice is worth 3 points, a 2nd 2 and a 3rd 1."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

POINTS_PER_PLACE = (3, 2, 1)


@dataclass(frozen=True)
class Tally:
    """How many ballots put a nominee 1st, 2nd and 3rd."""
    nominee: str
    firsts: int = 0
    seconds: int = 0
    thirds: int = 0

    @property
    def points(self) -> int:
        return sum(points * count for points, count in zip(POINTS_PER_PLACE, self.counts))

    @property
    def counts(self) -> tuple[int, int, int]:
        return self.firsts, self.seconds, self.thirds

    @property
    def standing(self) -> tuple[int, int, int, int]:
        """What decides the order: points, then the most 1st choices, then 2nd, then 3rd."""
        return self.points, self.firsts, self.seconds, self.thirds


@dataclass(frozen=True)
class Placing:
    """A nominee's place. Nominees level on every count share a rank and are marked tied."""
    rank: int
    tally: Tally
    tied: bool


def count_ballots(ballots: Iterable[tuple[str, str, str]]) -> list[Tally]:
    """Tallies (1st, 2nd, 3rd choice) ballots, one Tally per nominee that appears on any of them."""
    counts: dict[str, list[int]] = {}
    for ballot in ballots:
        for place, nominee in enumerate(ballot):
            counts.setdefault(nominee, [0, 0, 0])[place] += 1
    return [Tally(nominee, *places) for nominee, places in counts.items()]


def rank_tallies(tallies: Iterable[Tally]) -> list[Placing]:
    """
    Orders nominees best first. Nominees level on every count share a rank (1, 2, 2, 4) and are listed
    alphabetically, so the order never depends on who voted first.
    """
    ordered = sorted(tallies, key=lambda t: ([-n for n in t.standing], t.nominee.casefold()))
    level = Counter(tally.standing for tally in ordered)

    placings = []
    for position, tally in enumerate(ordered, start=1):
        same_as_previous = placings and placings[-1].tally.standing == tally.standing
        rank = placings[-1].rank if same_as_previous else position
        placings.append(Placing(rank, tally, level[tally.standing] > 1))
    return placings


def tied_for_first(placings: list[Placing]) -> list[str]:
    """The nominees level for 1st place on every count (empty when 1st place is decided)."""
    leaders = [placing.tally.nominee for placing in placings if placing.rank == 1]
    return leaders if len(leaders) > 1 else []
