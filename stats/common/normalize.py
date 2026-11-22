"""
Matching the same artist or song however it was typed: case, spacing, punctuation, curly quotes,
"feat." credits, a trailing "(Eng. Ver.)" and the community's nicknames for some groups.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Hashable

# Normalized artist key -> the key it's counted as. Keys are lowercase with every space and punctuation
# mark removed (see norm_key). Add to this as new spellings show up in the data notes.
ARTIST_ALIASES = {
    "asepa": "aespa",
    "billie": "billlie",
    "booseoksoon": "bss",
    "huntix": "huntrx",
    "huntrix": "huntrx",
    "idle": "gidle",
    "kirras": "kiiras",
    "kol": "kissoflife",
    "kwaneunbi": "kwoneunbi",
    "loonaoec": "loonaoddeyecircle",
    "lsrm": "lesserafim",
    "madeins": "madein",
    "nwjns": "newjeans",
    "oddeyecircle": "loonaoddeyecircle",
    "skz": "straykids",
    "tommorowxtogether": "txt",
    "tomorrowxtogether": "txt",
    "zerobaseone": "zb1",
}

FEATURING = re.compile(r"\s*[(\[]?\s*\b(?:feat|ft)\b\.?\s.*$", re.IGNORECASE)
# A parenthetical that ends a word, e.g. "UFO (Attention)" or "Tiki-Taka(99%)", but not "FRI(END)S",
# "(G)I-DLE" or "ALL(H)OURS"
PARENTHETICAL = re.compile(r"\s*[(\[][^)\]]*[)\]](?=\s|$)")


def norm_key(text: str) -> str:
    """Lowercase, with every space, punctuation mark and symbol removed."""
    return re.sub(r"[\W_]+", "", text.casefold())


def _base(text: str) -> str:
    """The name without a "feat." credit or a trailing parenthetical (unless that's all there is)."""
    return PARENTHETICAL.sub("", FEATURING.sub("", text)).strip() or text.strip()


def artist_key(artist: str) -> str:
    key = norm_key(_base(artist))
    return ARTIST_ALIASES.get(key, key)


def song_key(song: str) -> str:
    return norm_key(_base(song).replace("&", " and "))


def display_artist(artist: str) -> str:
    """The artist as shown in reports: as typed, without a "feat." credit."""
    return _base(artist)


class Names:
    """Every spelling seen for a key; a report shows the most common one (the first seen on a tie)."""

    def __init__(self):
        self._seen: dict[Hashable, Counter] = defaultdict(Counter)

    def add(self, key: Hashable, spelling: str):
        self._seen[key][" ".join(spelling.split())] += 1

    def __getitem__(self, key: Hashable) -> str:
        return self._seen[key].most_common(1)[0][0]

    def merged(self) -> list[tuple[Hashable, list[str]]]:
        """The keys typed more than one way, beyond capital letters, with their spellings (most common first)."""
        groups = []
        for key, spellings in self._seen.items():
            if len({spelling.casefold() for spelling in spellings}) > 1:
                groups.append((key, [spelling for spelling, _ in spellings.most_common()]))
        return sorted(groups, key=lambda group: group[1][0].casefold())
