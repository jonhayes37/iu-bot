"""How alike two members' lists are, with and without regard to where each song was placed."""

import itertools
from collections.abc import Callable, Hashable, Mapping, Sequence

Similarity = Callable[[Sequence[Hashable], Sequence[Hashable]], float]


def shared_songs(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    """The share of a's songs that are also on b, 0 to 100%."""
    if not a:
        return 0.0
    return 100.0 * len(set(a) & set(b)) / len(a)


def shared_by_position(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    """
    Like shared_songs, but each shared song counts less the further apart the two lists placed it: fully
    at the same spot, (n - k) / n when k places apart, for a list of n.
    """
    if not a:
        return 0.0
    n = len(a)
    place_a = {song: i for i, song in enumerate(a)}
    place_b = {song: i for i, song in enumerate(b)}
    weight = sum((n - abs(place_a[song] - place_b[song])) / n for song in place_a.keys() & place_b.keys())
    return 100.0 * weight / n


def closest_lists(lists: Mapping[str, Sequence[Hashable]], similarity: Similarity,
                  top_n: int = 3) -> dict[str, list[tuple[str, float]]]:
    """Each member's top_n most similar lists, most similar first (by name when level)."""
    scores: dict[str, list[tuple[str, float]]] = {member: [] for member in lists}
    for a, b in itertools.combinations(lists, 2):
        scores[a].append((b, similarity(lists[a], lists[b])))
        scores[b].append((a, similarity(lists[b], lists[a])))
    return {member: sorted(others, key=lambda pair: (-pair[1], pair[0].casefold()))[:top_n]
            for member, others in scores.items()}
