"""Matching artists and songs however they were typed."""

import pytest

from stats.common.normalize import Names, artist_key, display_artist, norm_key, song_key


@pytest.mark.parametrize("a, b", [
    ("IVE", "Ive"),
    ("Kang Daniel", "KangDaniel"),
    ("Wanna One ", "Wanna One"),
    ("TWS ft 24KGoldn", "TWS"),
    ("Rohann (feat Vinxen)", "Rohann"),
    ("Jessica ft. Fabolous", "Jessica"),
    ("SKZ", "Stray Kids"),
    ("i-dle", "(G)I-DLE"),
    ("Zerobaseone", "ZB1"),
])
def test_the_same_artist_however_it_was_typed(a, b):
    assert artist_key(a) == artist_key(b)


@pytest.mark.parametrize("a, b", [
    ("Like Magic", "Like Magic"),
    ("ALL(H)OURS", "ALLHOURS"),
])
def test_parentheses_inside_a_name_are_kept(a, b):
    assert artist_key(a) == artist_key(b) == norm_key(b)


@pytest.mark.parametrize("a, b", [
    ("I DONT CARE", "I DON'T CARE"),
    ("Moonwalkin’", "Moonwalkin'"),
    ("Moonlight (Eng. Ver.)", "Moonlight"),
    ("Get Out (Feat. Wow)", "Get Out"),
    ("Love & War", "Love and War"),
])
def test_the_same_song_however_it_was_typed(a, b):
    assert song_key(a) == song_key(b)


def test_different_songs_stay_different():
    assert song_key("Bang Bang") != song_key("Bang")


def test_a_name_that_is_only_a_parenthetical_is_kept():
    assert song_key("(Intro)") == "intro"


def test_display_artist_drops_the_featuring_credit():
    assert display_artist("Kang Daniel ft. Chung Ha") == "Kang Daniel"


class TestNames:
    """Showing the most common spelling."""

    def test_shows_the_most_common_spelling(self):
        names = Names()
        for spelling in ("Billlie", "BILLLIE", "BILLLIE"):
            names.add("billlie", spelling)

        assert names["billlie"] == "BILLLIE"

    def test_the_first_spelling_wins_a_tie(self):
        names = Names()
        names.add("ive", "IVE")
        names.add("ive", "Ive")

        assert names["ive"] == "IVE"

    def test_merged_lists_keys_typed_differently_beyond_capitals(self):
        names = Names()
        for key, spelling in (("ive", "IVE"), ("ive", "Ive"), ("kd", "Kang Daniel"), ("kd", "KangDaniel"),
                              ("kd", "Kang  Daniel")):
            names.add(key, spelling)

        assert names.merged() == [("kd", ["Kang Daniel", "KangDaniel"])]
