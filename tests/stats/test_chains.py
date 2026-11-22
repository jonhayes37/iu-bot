"""Chaining What Are You Listening To lists through shared songs."""

from stats.common.chains import find_chains


def test_links_everyone_into_one_chain_when_possible():
    lists = {"A": ["x", "a1"], "B": ["x", "y"], "C": ["y", "z"], "D": ["z", "d1"]}

    result = find_chains(lists)

    assert result.chains == [[("A", "x"), ("B", "y"), ("C", "z"), ("D", None)]]
    assert not result.timed_out


def test_a_member_cant_be_linked_in_and_out_by_the_same_song():
    # Everyone shares only "x": A -> B -> C would use x twice through B
    result = find_chains({"A": ["x"], "B": ["x"], "C": ["x"]})

    assert [len(chain) for chain in result.chains] == [2]


def test_no_shared_songs_means_no_chains():
    assert not find_chains({"A": ["x"], "B": ["y"]}).chains


def test_prefers_fewer_chains_when_as_many_members_are_linked():
    lists = {"A": ["p"], "B": ["p", "q"], "C": ["q", "r"], "D": ["r"]}

    assert [len(chain) for chain in find_chains(lists).chains] == [4]


def test_gives_up_at_the_time_limit():
    lists = {name: ["x"] for name in "ABCDEF"}

    assert find_chains(lists, time_limit=-1).timed_out
