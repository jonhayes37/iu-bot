"""Who shares whose taste: shared songs, taste groups, group favourites and bridging songs."""

import networkx as nx

from stats.common.network import MAX_GROUPS, bridging_songs, connect, group_favourites, taste_groups

# Two clear camps (a, b, c / x, y, z) that only meet over the song "bridge"
LISTS = {
    "a": ["s1", "s2", "s3", "bridge"],
    "b": ["s1", "s2", "s3", "b1"],
    "c": ["s1", "s2", "c1", "c2"],
    "x": ["t1", "t2", "t3", "bridge"],
    "y": ["t1", "t2", "t3", "y1"],
    "z": ["t1", "t2", "z1", "z2"],
    "loner": ["l1", "l2", "l3", "l4"],
}


def test_shared_songs_per_pair():
    connections = connect(LISTS)

    assert connections.shared[frozenset(("a", "b"))] == ["s1", "s2", "s3"]
    assert connections.count("a", "x") == 1
    assert connections.count("a", "loner") == 0
    assert frozenset(("a", "loner")) not in connections.shared


def test_a_song_listed_twice_counts_once():
    assert connect({"a": ["s", "s"], "b": ["s"]}).count("a", "b") == 1


def test_finds_the_two_camps():
    connections = connect(LISTS)

    assert sorted(sorted(group) for group in connections.groups) == [["a", "b", "c"], ["x", "y", "z"]]
    assert connections.ungrouped == ["loner"]
    assert connections.group_of("loner") is None
    assert connections.group_of("a") != connections.group_of("x")


def test_partners_most_shared_first():
    assert connect(LISTS).partners("a") == [("b", 3), ("c", 2), ("x", 1)]


def test_the_graph_weights_edges_by_shared_songs():
    graph = connect(LISTS).graph()

    assert graph["a"]["b"]["weight"] == 3
    assert "loner" in graph and not graph["loner"]


def test_group_favourites_and_bridges():
    connections = connect(LISTS)
    group = next(g for g in connections.groups if "a" in g)

    assert group_favourites(connections, group)[:2] == [("s1", 3), ("s2", 3)]
    assert bridging_songs(connections) == [("bridge", 2, 2)]


def test_no_shared_songs_means_no_groups():
    connections = connect({"a": ["1"], "b": ["2"]})

    assert not connections.groups
    assert connections.ungrouped == ["a", "b"]


def test_groups_past_the_colour_limit_are_ungrouped(monkeypatch):
    camps = {f"{camp}{i}": [f"{camp}-song-{j}" for j in range(3)] for camp in "pqrs" for i in range(2)}
    monkeypatch.setattr("stats.common.network.taste_groups",
                        lambda graph: [[f"{camp}0", f"{camp}1"] for camp in "pqrs"])

    connections = connect(camps)

    assert len(connections.groups) == MAX_GROUPS
    assert connections.ungrouped == ["s0", "s1"]


def test_taste_groups_skip_members_on_their_own():
    graph = nx.Graph()
    graph.add_edge("a", "b", weight=3)
    graph.add_node("solo")

    assert taste_groups(graph) == [["a", "b"]]


def test_more_camps_than_colours_are_merged_rather_than_greyed_out():
    # Four tight camps of three, each linked to the next by one shared song: Louvain's usual split is four groups
    lists = {}
    for camp in range(4):
        for member in range(3):
            links = [f"link-{camp}", f"link-{(camp + 1) % 4}"]
            lists[f"c{camp}m{member}"] = [f"c{camp}-song-{j}" for j in range(4)] + links

    connections = connect(lists)

    assert len(connections.groups) <= MAX_GROUPS
    assert not connections.ungrouped
    for camp in range(4):  # a camp is never split up
        assert len({connections.group_of(f"c{camp}m{member}") for member in range(3)}) == 1
