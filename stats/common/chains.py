"""
Chaining What Are You Listening To lists together: A shares a song with B, B shares a different song
with C, and so on, so the video can flow from one member's picks to the next. Finds the arrangement
that links the most members, then the fewest separate chains.
"""

import time
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass

TIME_LIMIT_SECONDS = 10  # fine for the ~20 lists a video gets; past that it returns the best found so far


@dataclass(frozen=True)
class Link:
    """source's list leads into target's through a song on both."""
    source: str
    target: str
    song: Hashable


@dataclass(frozen=True)
class ChainResult:
    """The best chains found, longest first."""
    chains: list[list[tuple[str, Hashable | None]]]  # each member, with the song linking them to the next
    timed_out: bool


def _possible_links(lists: Mapping[str, Sequence[Hashable]]) -> dict[str, list[tuple[str, Hashable]]]:
    return {source: [(target, song) for target in lists if target != source
                     for song in dict.fromkeys(lists[source]) if song in set(lists[target])]
            for source in lists}


def find_chains(lists: Mapping[str, Sequence[Hashable]], time_limit: float = TIME_LIMIT_SECONDS) -> ChainResult:
    """
    Each member links to at most one other and from at most one, with no loops, and a member can't be
    linked in and out by the same song. Tries every arrangement (up to time_limit seconds).
    """
    members = list(lists)
    possible = _possible_links(lists)
    link_in: dict[str, Link | None] = dict.fromkeys(members)
    link_out: dict[str, Link | None] = dict.fromkeys(members)
    best: list[Link] = []
    best_score = (0, 0)
    perfect = (len(members), len(members) - 1)  # everyone in one chain
    deadline = time.monotonic() + time_limit
    timed_out = False

    def score() -> tuple[int, int]:
        # Most members linked first; then most links, which is the same as fewest chains
        linked = sum(1 for m in members if link_in[m] or link_out[m])
        return linked, sum(1 for m in members if link_out[m])

    def makes_loop(source: str, target: str) -> bool:
        current = target
        while current is not None:
            if current == source:
                return True
            current = link_out[current].target if link_out[current] else None
        return False

    def allowed(source: str, target: str, song: Hashable) -> bool:
        return (link_in[target] is None
                and not (link_in[source] and link_in[source].song == song)
                and not (link_out[target] and link_out[target].song == song)
                and not makes_loop(source, target))

    def search(index: int) -> bool:
        """True once a perfect arrangement is found (nothing can beat it)."""
        nonlocal best, best_score, timed_out
        if timed_out or time.monotonic() > deadline:
            timed_out = True
            return False
        if index == len(members):
            if score() > best_score:
                best_score = score()
                best = [link for link in link_out.values() if link]
            return best_score == perfect
        source = members[index]
        for target, song in possible[source]:
            if allowed(source, target, song):
                link_out[source] = link_in[target] = Link(source, target, song)
                found = search(index + 1)
                link_out[source] = link_in[target] = None
                if found:
                    return True
        return search(index + 1)

    search(0)
    return ChainResult(_chains_from(best), timed_out)


def _chains_from(links: list[Link]) -> list[list[tuple[str, Hashable | None]]]:
    following = {link.source: link for link in links}
    targets = {link.target for link in links}
    chains = []
    for start in (link.source for link in links if link.source not in targets):
        chain, member = [], start
        while member in following:
            chain.append((member, following[member].song))
            member = following[member].target
        chain.append((member, None))
        chains.append(chain)
    return sorted(chains, key=len, reverse=True)
