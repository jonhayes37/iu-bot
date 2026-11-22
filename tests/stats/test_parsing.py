"""Reading IU's list exports."""

import pytest

from stats.common.parsing import ListFileError, Pick, Submission, load_lists, make_pick, split_pick


class TestLoadLists:
    """Reading a whole file."""

    def test_reads_each_members_list_from_the_export(self, list_file):
        path = list_file("""
            --- Jo ---
            1. IVE // Bang Bang
            2. Billlie // Work

            --- Sam Smith! ---
            1. ITZY // Motto
            2. aespa // Dirty Work
        """)

        assert load_lists(path) == [
            Submission("Jo", (Pick(1, "IVE // Bang Bang", "IVE", "Bang Bang"),
                              Pick(2, "Billlie // Work", "Billlie", "Work"))),
            Submission("Sam Smith!", (Pick(1, "ITZY // Motto", "ITZY", "Motto"),
                                      Pick(2, "aespa // Dirty Work", "aespa", "Dirty Work"))),
        ]

    def test_a_username_that_starts_with_a_number_is_still_a_header(self, list_file):
        path = list_file("--- 1. Jo ---\n1. A // a\n")

        assert [s.user for s in load_lists(path)] == ["1. Jo"]

    def test_a_member_with_an_empty_list_is_left_out(self, list_file):
        path = list_file("--- Jo ---\n\n--- Sam ---\n1. A // a\n")

        assert [s.user for s in load_lists(path)] == ["Sam"]

    def test_accepts_the_expected_number_of_picks(self, list_file):
        path = list_file("--- Jo ---\n1. A // a\n2. B // b\n")

        assert len(load_lists(path, expected_count=2)[0].picks) == 2

    def test_every_problem_is_named_at_once(self, list_file):
        path = list_file("""
            1. A // a
            Jo
            --- Sam ---
            1. A // a
            3. B // b
            --- Sam ---
            1. C // c
        """)

        with pytest.raises(ListFileError) as error:
            load_lists(path, expected_count=2)

        message = str(error.value)
        assert "line 1: a pick before the first '--- username ---' line" in message
        assert "line 2: expected '--- username ---' or a numbered pick, found 'Jo'" in message
        assert "line 6: Sam has a second list" in message
        assert "Sam: 1 picks, expected 2" in message

    def test_numbering_must_run_from_one(self, list_file):
        path = list_file("--- Jo ---\n1. A // a\n3. B // b\n")

        with pytest.raises(ListFileError, match="Jo: the picks aren't numbered 1, 2, 3"):
            load_lists(path)


class TestPicks:
    """Splitting one line into artist and song."""

    @pytest.mark.parametrize("text, expected", [
        ("IVE // Bang Bang", ("IVE", "Bang Bang")),
        ("IVE//Bang Bang", ("IVE", "Bang Bang")),
        ("IVE /// Bang Bang", ("IVE", "Bang Bang")),
        ("IVE /. Bang Bang", ("IVE", "Bang Bang")),
        ("IVE - Bang Bang", ("IVE", "Bang Bang")),
        ("H1-KEY // Rose Blossom", ("H1-KEY", "Rose Blossom")),
        ("IVE Bang Bang", None),
        ("// Bang Bang", None),
    ])
    def test_split_pick(self, text, expected):
        assert split_pick(text) == expected

    def test_a_line_without_a_separator_is_a_song_with_no_artist(self):
        assert make_pick(3, "IVE Bang Bang") == Pick(3, "IVE Bang Bang", None, "IVE Bang Bang")

    def test_quotes_around_a_pick_are_dropped(self):
        assert make_pick(1, ' "IVE // Bang Bang" ') == Pick(1, "IVE // Bang Bang", "IVE", "Bang Bang")
