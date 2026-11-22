"""Counting picks and points, and ranking with tiebreaks."""

import random

import pytest

from stats.common.parsing import Submission, make_pick
from stats.common.tally import Tallies, Tally, competition_ranks, points_for, rank_by_points


def submission(user, *picks):
    return Submission(user, tuple(make_pick(rank, text) for rank, text in enumerate(picks, start=1)))


@pytest.mark.parametrize("rank, ranked, points", [(1, 15, 15), (15, 15, 1), (16, 15, 0), (1, None, 0)])
def test_points_for(rank, ranked, points):
    assert points_for(rank, ranked) == points


class TestTallies:
    """Counting every song and artist."""

    def test_counts_points_picks_and_firsts(self):
        tallies = Tallies([submission("Jo", "IVE // Bang Bang", "ITZY // Motto", "IVE // Rebel Heart"),
                           submission("Sam", "ive // BANG BANG", "IVE // Bang Bang", "Billlie // Work")], ranked=2)

        bang_bang = tallies.songs[("ive", "bangbang")]
        assert (bang_bang.points, bang_bang.picks, bang_bang.firsts) == (5, 3, 2)
        assert bang_bang.pickers == ["Jo", "Sam", "Sam"]
        assert bang_bang.firsts_by == ["Jo", "Sam"]
        ive = tallies.artists["ive"]
        assert (ive.points, ive.picks, ive.firsts) == (5, 4, 2)
        assert list(ive.songs) == [("ive", "bangbang"), ("ive", "rebelheart")]

    def test_names_use_the_most_common_spelling(self):
        tallies = Tallies([submission("Jo", "ive // bang bang"), submission("Sam", "IVE // Bang Bang"),
                           submission("Al", "IVE // Bang Bang")])

        assert tallies.song_name(("ive", "bangbang")) == "IVE // Bang Bang"
        assert tallies.title(("ive", "bangbang")) == "Bang Bang"
        assert tallies.artist_name("ive") == "IVE"

    def test_a_pick_with_no_artist_is_a_song_on_its_own(self):
        tallies = Tallies([submission("Jo", "IVE Bang Bang")], ranked=1)

        assert tallies.songs[(None, "ivebangbang")].points == 1
        assert tallies.song_name((None, "ivebangbang")) == "IVE Bang Bang"
        assert not tallies.artists
        assert [(user, pick.text) for user, pick in tallies.unsplit] == [("Jo", "IVE Bang Bang")]

    def test_merged_spellings_name_the_artist_of_a_song(self):
        tallies = Tallies([submission("Jo", "Baby DONT Cry // I DONT CARE", "Kang Daniel // Paranoia"),
                           submission("Sam", "Baby DONT Cry // I DON'T CARE", "KangDaniel // Paranoia")])

        assert tallies.merged_spellings() == [
            ["Kang Daniel", "KangDaniel"],
            ["Baby DONT Cry // I DONT CARE", "Baby DONT Cry // I DON'T CARE"],
        ]


class TestRankByPoints:
    """Points, then #1s, then picks, then a seeded draw."""

    def test_most_points_then_most_firsts_then_most_picks(self):
        tallies = [Tally("fewer points", points=9, firsts=5, picks=9), Tally("more picks", points=10, picks=3),
                   Tally("more firsts", points=10, firsts=1, picks=1), Tally("most points", points=11)]

        placings = rank_by_points(tallies, random.Random(1))

        assert [(p.place, p.tally.key, p.drawn) for p in placings] == [
            (1, "most points", False), (2, "more firsts", False), (3, "more picks", False),
            (4, "fewer points", False)]

    def test_a_full_tie_is_drawn_the_same_way_for_the_same_seed(self):
        tallies = [Tally(name, points=5, firsts=1, picks=2) for name in "abcdefgh"] + [Tally("top", points=9)]

        first = [p.tally.key for p in rank_by_points(tallies, random.Random(42))]
        again = [p.tally.key for p in rank_by_points(reversed(tallies), random.Random(42))]
        draws = {tuple(p.tally.key for p in rank_by_points(tallies, random.Random(seed))) for seed in range(20)}

        assert first == again
        assert first[0] == "top"
        assert len(draws) > 1
        assert [p.drawn for p in rank_by_points(tallies, random.Random(42))] == [False] + [True] * 8


def test_competition_ranks_share_a_rank_when_level():
    assert competition_ranks([5, 3, 3, 1], lambda n: n) == [(1, 5), (2, 3), (2, 3), (4, 1)]
