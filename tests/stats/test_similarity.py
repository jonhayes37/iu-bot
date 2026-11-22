"""Comparing members' lists."""

import pytest

from stats.common.similarity import closest_lists, shared_by_position, shared_songs


@pytest.mark.parametrize("a, b, score", [
    ("abcd", "abcd", 100.0),
    ("abcd", "dcxy", 50.0),
    ("abcd", "wxyz", 0.0),
    ("", "abcd", 0.0),
])
def test_shared_songs(a, b, score):
    assert shared_songs(list(a), list(b)) == score


@pytest.mark.parametrize("a, b, score", [
    ("abcd", "abcd", 100.0),
    ("abcd", "bacd", 100.0 * (2 + 3 / 4 + 3 / 4) / 4),  # a and b each one place apart
    ("abcd", "xyza", 100.0 * (1 / 4) / 4),  # a three places apart
    ("abcd", "wxyz", 0.0),
    ("", "abcd", 0.0),
])
def test_shared_by_position(a, b, score):
    assert shared_by_position(list(a), list(b)) == pytest.approx(score)


def test_closest_lists_most_similar_first_then_by_name():
    lists = {"Jo": list("abcd"), "Sam": list("abxy"), "Al": list("abcx"), "Bo": list("abxz"), "Cy": list("wxyz")}

    closest = closest_lists(lists, shared_songs, top_n=3)

    assert closest["Jo"] == [("Al", 75.0), ("Bo", 50.0), ("Sam", 50.0)]
    assert closest["Cy"] == [("Bo", 50.0), ("Sam", 50.0), ("Al", 25.0)]
