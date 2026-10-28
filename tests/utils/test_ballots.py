"""Tests for utils/ballots.py: counting ranked ballots and breaking ties."""

import pytest

from utils.ballots import Placing, Tally, count_ballots, rank_tallies, tied_for_first


class TestTally:
    """Points are 3 for a 1st choice, 2 for a 2nd and 1 for a 3rd."""

    @pytest.mark.parametrize("counts, points", [((0, 0, 0), 0), ((1, 0, 0), 3), ((0, 1, 0), 2), ((0, 0, 1), 1),
                                                ((2, 3, 4), 16)])
    def test_points(self, counts, points):
        assert Tally("A", *counts).points == points


class TestCountBallots:
    """Each nominee on any ballot gets a tally of its 1st, 2nd and 3rd choices."""

    def test_no_ballots(self):
        assert count_ballots([]) == []

    def test_counts_each_place_separately(self):
        tallies = count_ballots([("A", "B", "C"), ("B", "A", "C"), ("A", "C", "D")])

        assert sorted(tallies, key=lambda t: t.nominee) == [
            Tally("A", 2, 1, 0), Tally("B", 1, 1, 0), Tally("C", 0, 1, 2), Tally("D", 0, 0, 1)]


class TestRankTallies:
    """Points first, then the most 1st choices, then 2nd, then 3rd."""

    def test_more_points_wins(self):
        placings = rank_tallies([Tally("Low", 0, 0, 1), Tally("High", 1, 0, 0)])

        assert [(p.rank, p.tally.nominee, p.tied) for p in placings] == [(1, "High", False), (2, "Low", False)]

    def test_equal_points_go_to_the_most_first_choices(self):
        # 3 points each: one 1st choice beats a 2nd and a 3rd
        placings = rank_tallies([Tally("Spread", 0, 1, 1), Tally("Firsts", 1, 0, 0)])

        assert [p.tally.nominee for p in placings] == ["Firsts", "Spread"]
        assert not any(p.tied for p in placings)

    def test_then_the_most_second_choices(self):
        # 6 points and one 1st choice each
        placings = rank_tallies([Tally("Thirds", 1, 0, 3), Tally("Seconds", 1, 1, 1)])

        assert [p.tally.nominee for p in placings] == ["Seconds", "Thirds"]

    def test_level_on_every_count_share_the_rank_alphabetically(self):
        placings = rank_tallies([Tally("b", 1, 1, 0), Tally("Top", 2, 0, 0), Tally("A", 1, 1, 0),
                                 Tally("Last", 0, 0, 1)])

        assert placings == [Placing(1, Tally("Top", 2, 0, 0), False), Placing(2, Tally("A", 1, 1, 0), True),
                            Placing(2, Tally("b", 1, 1, 0), True), Placing(4, Tally("Last", 0, 0, 1), False)]


class TestTiedForFirst:
    """A tie for 1st on every count is flagged for a tiebreaker."""

    def test_a_clear_winner_needs_no_tiebreaker(self):
        assert tied_for_first(rank_tallies([Tally("A", 2, 0, 0), Tally("B", 1, 1, 0)])) == []

    def test_a_tie_lower_down_needs_no_tiebreaker(self):
        assert tied_for_first(rank_tallies([Tally("A", 3, 0, 0), Tally("B", 1, 0, 0), Tally("C", 1, 0, 0)])) == []

    def test_everyone_level_for_first_is_listed(self):
        placings = rank_tallies([Tally("C", 1, 1, 1), Tally("A", 1, 1, 1), Tally("B", 1, 1, 1), Tally("D", 0, 1, 0)])

        assert tied_for_first(placings) == ["A", "B", "C"]

    def test_nothing_to_rank(self):
        assert tied_for_first([]) == []
