"""
Who shares whose taste: the songs each pair of members both picked, and the taste groups that come out
of it (community detection on the network of members, joined by how many songs they share).
"""

import itertools
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import networkx as nx
from networkx.algorithms.community import louvain_communities

from stats.common.tally import SongKey

GROUP_SEED = 1  # Louvain is randomised; a fixed seed gives the same groups every run
MAX_GROUPS = 3  # only three group colours stay distinct for colour-blind readers
# Louvain's resolution, finest first: 1 is its standard split; lower values merge groups into fewer, bigger ones
RESOLUTIONS = tuple(r / 10 for r in range(10, 0, -1))


@dataclass(frozen=True)
class Connections:
    """Every member's list, what each pair shares, and the taste groups (largest first)."""
    lists: dict[str, list[SongKey]]
    shared: dict[frozenset[str], list[SongKey]]  # only pairs sharing at least one song
    groups: list[list[str]]  # at most MAX_GROUPS; anyone else is in `ungrouped`
    ungrouped: list[str]

    @property
    def members(self) -> list[str]:
        return list(self.lists)

    def count(self, a: str, b: str) -> int:
        return len(self.shared.get(frozenset((a, b)), []))

    def group_of(self, member: str) -> int | None:
        """The member's group's index, or None when they're in no group."""
        return next((i for i, group in enumerate(self.groups) if member in group), None)

    def partners(self, member: str) -> list[tuple[str, int]]:
        """Everyone the member shares a song with, most shared first (by name when level)."""
        return sorted(((other, self.count(member, other)) for other in self.lists
                       if other != member and self.count(member, other)), key=lambda p: (-p[1], p[0].casefold()))

    def graph(self) -> nx.Graph:
        """Members, joined by an edge weighted by the number of songs they share."""
        graph = nx.Graph()
        graph.add_nodes_from(self.lists)
        for pair, songs in self.shared.items():
            graph.add_edge(*sorted(pair), weight=len(songs))
        return graph


def connect(lists: Mapping[str, Sequence[SongKey]]) -> Connections:
    lists = {member: list(dict.fromkeys(songs)) for member, songs in lists.items()}
    shared = {}
    for a, b in itertools.combinations(lists, 2):
        in_b = set(lists[b])
        songs = [song for song in lists[a] if song in in_b]  # in a's order
        if songs:
            shared[frozenset((a, b))] = songs
    connections = Connections(lists, shared, [], [])
    groups = taste_groups(connections.graph())
    grouped = {member for group in groups[:MAX_GROUPS] for member in group}
    return Connections(lists, shared, groups[:MAX_GROUPS], [m for m in lists if m not in grouped])


def taste_groups(graph: nx.Graph) -> list[list[str]]:
    """
    Members who share more songs with each other than with everyone else, largest group first. Each
    group's members are listed by how many songs they share inside the group.

    The number of groups comes from the data, up to MAX_GROUPS: when Louvain finds more, it's asked for
    a coarser split (a lower resolution, which merges the closest groups) until there are few enough.
    A member who shares too little to belong anywhere stays on their own and is left out.
    """
    if not graph.number_of_edges():
        return []
    for resolution in RESOLUTIONS:
        found = louvain_communities(graph, weight="weight", seed=GROUP_SEED, resolution=resolution)
        if sum(1 for community in found if len(community) > 1) <= MAX_GROUPS:
            break
    groups = []
    for community in found:
        if len(community) < 2:
            continue
        inside = {m: sum(graph[m][o]["weight"] for o in graph[m] if o in community) for m in community}
        groups.append(sorted(community, key=lambda m, inside=inside: (-inside[m], m.casefold())))
    return sorted(groups, key=lambda group: (-len(group), group[0].casefold()))


def group_favourites(connections: Connections, group: Sequence[str]) -> list[tuple[SongKey, int]]:
    """The songs most members of the group picked (2 or more), most picked first."""
    counts = Counter(song for member in group for song in connections.lists[member])
    return sorted(((song, n) for song, n in counts.items() if n > 1), key=lambda item: -item[1])


def bridging_songs(connections: Connections) -> list[tuple[SongKey, int, int]]:
    """Songs picked in more than one taste group: (song, groups it reached, members who picked it)."""
    reach: dict[SongKey, set[int]] = {}
    pickers: Counter = Counter()
    for member, songs in connections.lists.items():
        group = connections.group_of(member)
        for song in songs:
            pickers[song] += 1
            if group is not None:
                reach.setdefault(song, set()).add(group)
    rows = [(song, len(groups), pickers[song]) for song, groups in reach.items() if len(groups) > 1]
    return sorted(rows, key=lambda row: (-row[1], -row[2]))
