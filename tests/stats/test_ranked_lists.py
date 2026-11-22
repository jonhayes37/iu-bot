"""The Top 100, Top 15 So Far and All-Time Top 15 reports."""

import random
from pathlib import Path

import pytest
from testsupport.stats_lists import export, table_rows

from stats.common.parsing import ListFileError
from stats.ranked_lists import FORMATS, ListFormat, RankedListReport, main, year_of

SAMPLES = Path(__file__).resolve().parents[2] / "stats" / "data"
TOP_3 = ListFormat("Top 3 ({year})", ranked=3, cutoff=2, ranking_rows=4)


def build(fmt, path, tmp_path, seed=1):
    return RankedListReport(fmt, path, seed).build(tmp_path / "out").text()


def section(text, title):
    """One section of the report, from its title to the next."""
    after = text.split(f"\n\n\n{title}\n", 1)[1]
    return after.split("\n\n\n", 1)[0]


def test_year_of():
    assert year_of(Path("mid_year_2026_stats.txt")) == "2026"
    assert year_of(Path("lists.txt")) == ""


class TestPointsRanking:
    """The points ranking and its tiebreaks."""

    def test_ties_go_to_the_most_firsts_then_the_most_picks(self, list_file, tmp_path):
        # All on 4 points. A: 3 + 1, with a #1. B: 1 + 2 + 1, three picks. C: 2 + 2, two picks.
        path = list_file(export(("Jo", ["X // A", "X // C", "X // B"]), ("Sam", ["X // P", "X // C", "X // A"]),
                                ("Al", ["X // Q", "X // B", "X // R"]), ("Bo", ["X // S", "X // T", "X // B"])))

        ranking = section(build(TOP_3, path, tmp_path), "Top 2 songs by points")

        rows = [row[:2] for row in table_rows(ranking) if len(row) > 1 and row[1].startswith("X // ")]
        assert rows[:3] == [["1", "X // A"], ["2", "X // B"], ["3", "X // C"]]

    def test_a_draw_across_the_cutoff_is_flagged(self, list_file, tmp_path):
        path = list_file(export(("Jo", ["X // A", "Y // B", "Z // C"]), ("Sam", ["X // D", "Y // E", "Z // F"])))

        text = build(TOP_3, path, tmp_path, seed=5)

        notes = section(text, "Data notes")
        assert "Places in the top 2 decided by the random draw (seed 5; add --seed 5 to repeat it): 1-2" in notes
        assert "The draw decided the Top 2 cutoff" not in notes
        assert "---- 2 make the video; the rest just missed out ----" in text

    def test_the_cutoff_draw_names_who_made_it(self, list_file, tmp_path):
        path = list_file(export(("Jo", ["X // A", "Y // B", "Z // C"]), ("Sam", ["X // A", "Y // E", "Z // F"])))

        notes = section(build(TOP_3, path, tmp_path), "Data notes")

        assert "Places in the top 2 decided by the random draw" in notes
        assert "⚠️ The draw decided the Top 2 cutoff:" in notes
        assert "(all level on points, #1s and picks)" in notes

    def test_the_same_seed_gives_the_same_report(self, list_file, tmp_path):
        path = list_file(export(*((name, ["X // A", "Y // B", "Z // C"][::step]) for name, step in
                                  (("Jo", 1), ("Sam", -1), ("Al", 1), ("Bo", -1)))))

        assert build(TOP_3, path, tmp_path, seed=9) == build(TOP_3, path, tmp_path, seed=9)


def test_the_all_time_ranking_is_of_artists(list_file, tmp_path):
    path = list_file(export(("Jo", ["Loona // Butterfly", "IVE // Baddie"] + [f"X{i} // s" for i in range(13)]),
                            ("Sam", ["Loona // Favorite", "Loona // New"] + [f"Y{i} // s" for i in range(13)])),
                     name="all_time_2026_stats.txt")

    text = build(FORMATS["all_time"], path, tmp_path)

    assert text.startswith("ALL-TIME TOP 15 (2026)")
    assert ["1", "Loona", "44", "2", "3", "3"] in table_rows(section(text, "Top artists by points"))
    assert "Butterfly (Jo), Favorite (Sam)" in section(text, "Most #1 picks")
    assert "Closest lists" not in text


def test_the_mid_year_report_has_every_section_and_a_chart(list_file, tmp_path):
    lists = [(name, [f"A{(i + n) % 20} // S{(i + n) % 20}" for i in range(16)]) for n, name in enumerate("JSAB")]
    path = list_file(export(*lists), name="mid_year_2026_stats.txt")

    text = build(FORMATS["mid_year"], path, tmp_path)

    for title in ("Top 15 songs by points", "Most #1 picks", "Most picked songs", "Most picked artists",
                  "Closest lists", "Closest lists, by position", "Closest to the overall Top 15", "Chart",
                  "Data notes"):
        assert f"\n{title}\n" in text
    assert "(honourable mentions count as picks)" in text
    assert (tmp_path / "out" / "mid_year_2026_stats_chart.png").exists()


def test_a_list_with_the_wrong_count_is_refused(list_file):
    path = list_file(export(("Jo", ["A // a"])))

    with pytest.raises(ListFileError, match="Jo: 1 picks, expected 16"):
        RankedListReport(FORMATS["mid_year"], path, 1)


class TestMain:
    """Running it from the command line."""

    def test_writes_the_report(self, list_file, tmp_path, capsys):
        path = list_file(export(("Jo", ["X // A", "Y // B", "Z // C"])))
        fmt = ListFormat("T", ranked=3)

        with pytest.MonkeyPatch.context() as patch:
            patch.setitem(FORMATS, "tiny", fmt)
            assert main(["tiny", str(path), "--out-dir", str(tmp_path / "out")]) == 0

        assert (tmp_path / "out" / "event_2026_stats_report.txt").exists()
        assert "Data notes" in capsys.readouterr().out

    def test_a_bad_file_is_reported(self, tmp_path, capsys):
        assert main(["mid_year", str(tmp_path / "missing.txt"), "--seed", "3"]) == 1

        assert capsys.readouterr().err.startswith("Error:")


@pytest.mark.parametrize("fmt, path", [
    ("top_100", "top_100/top_25_2025.txt"),
    ("mid_year", "mid_year/mid_year_2026_stats.txt"),
    ("all_time", "all_time/all_time_2026_stats.txt"),
])
def test_the_sample_exports_are_read_without_problems(fmt, path, tmp_path):
    text = RankedListReport(FORMATS[fmt], SAMPLES / path, random.Random(0).randrange(100)).build(tmp_path).text()

    assert "Couldn't find a clear spot" not in text
