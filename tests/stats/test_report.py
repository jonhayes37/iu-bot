"""Laying out the plain-text reports."""

import pytest

from stats.common.report import Report, display_width, write_report


@pytest.mark.parametrize("text, width", [("abc", 3), ("아이유", 6), ("Alexrandia 🖤", 13), ("é", 1), ("é", 1)])
def test_display_width(text, width):
    assert display_width(text) == width


def test_a_report_has_a_title_summary_and_sections():
    report = Report("Top 15", "14 lists")
    report.section("Most picked", "A note.")
    report.line("text")

    assert report.text() == "TOP 15\n======\n14 lists\n\n\nMost picked\n-----------\nA note.\ntext\n"


def test_tables_right_align_numbers_and_span_dividers():
    report = Report("T")
    report.table(["#", "Song", "Picks"], [["1", "아이유 // Love", 12], ["---- cutoff ----"], ["2*", "IVE // Bang", 3]])

    assert report.lines[2:] == [
        "#   Song            Picks",
        "--  --------------  -----",
        "1   아이유 // Love     12",
        "  ---- cutoff ----",
        "2*  IVE // Bang         3",
    ]


def test_an_empty_table_says_so():
    report = Report("T")
    report.table(["#"], [])

    assert report.lines[-1] == "(none)"


def test_write_report_prints_and_saves(tmp_path, capsys):
    path = write_report(Report("T"), "name", tmp_path / "out")

    assert path.read_text(encoding="utf-8") == "T\n=\n"
    assert capsys.readouterr().out.startswith("T\n=\n")
