"""The What Are You Listening To reports, for one video and all time."""

from pathlib import Path

from testsupport.stats_lists import export, table_rows

from stats import waylt, waylt_all_time

SAMPLE = Path(__file__).resolve().parents[2] / "stats" / "data" / "waylt" / "waylt_2026_10_stats.txt"


class TestWaylt:
    """One video's report."""

    def test_the_report_has_the_most_picked_and_the_chains(self, list_file):
        path = list_file(export(("Jo", ["IVE // Bang Bang", "ITZY // Motto"]),
                                ("Sam", ["ive // bang bang", "Billlie // Work"]),
                                ("Al", ["Billlie // Work", "Nobody else"])), name="waylt_2026_11_stats.txt")

        text = waylt.build_report(path).text()

        assert text.startswith("WHAT ARE YOU LISTENING TO (WAYLT_2026_11)")
        assert ["1", "IVE // Bang Bang", "2", "Jo, Sam"] in table_rows(text)
        assert "3 of 3 members linked in 1 chain(s)" in text
        assert "No '//' between artist and song, so counted as a song with no artist: Al #2 'Nobody else'" in text

    def test_no_shared_songs(self, list_file):
        path = list_file(export(("Jo", ["A // a"]), ("Sam", ["B // b"])))

        assert "No two lists share a song." in waylt.build_report(path).text()

    def test_the_sample_export(self):
        text = waylt.build_report(SAMPLE).text()

        assert "8 of 12 members linked in 2 chain(s)" in text
        assert "Nothing to note." in text

    def test_main(self, tmp_path, capsys):
        assert waylt.main([str(SAMPLE), "--out-dir", str(tmp_path)]) == 0
        assert (tmp_path / "waylt_2026_10_stats_report.txt").exists()
        assert waylt.main([str(tmp_path / "missing.txt")]) == 1
        assert "Error:" in capsys.readouterr().err


class TestWayltAllTime:
    """The report across every video."""

    def test_combines_the_spreadsheet_and_exports(self, list_file):
        sheet = list_file('Video,Jo,Sam\n'
                          'April 2023,"1. IVE // Bang Bang\n2. ITZY - Motto","Bang Bang // IVE\nWork // Billlie"\n'
                          ',ignored,\n'
                          'May 2023,"IVE // Bang Bang\nno separator here",\n', name="picks.csv")
        later = list_file(export(("Jo", ["IVE // Bang Bang"]), ("Al", ["Billlie // Work"])),
                          name="waylt_2026_10_stats.txt")

        text = waylt_all_time.build_report([sheet, later], top=20).text()

        assert "Videos: 3 (April 2023 to waylt_2026_10)" in text
        assert ["1", "IVE // Bang Bang", "4", "2", "April 2023, May 2023, waylt_2026_10", "Jo (x3), Sam"] \
            in table_rows(text)
        assert "Read as 'Song // Artist' and flipped: Sam, April 2023" in text
        assert "Skipped (no artist/song separator): Jo, May 2023: 'no separator here'" in text
        assert ["Jo", "4", "IVE (3)"] in table_rows(text)

    def test_ties_for_a_favourite_are_listed(self, list_file):
        path = list_file(export(("Jo", ["A // a", "B // b", "C // c", "D // d"])))

        assert ["Jo", "4", "A, B, C +1 more (1 each)"] in table_rows(waylt_all_time.build_report([path], top=5).text())

    def test_main(self, tmp_path, capsys):
        assert waylt_all_time.main([str(SAMPLE), "--top", "5", "--out-dir", str(tmp_path)]) == 0
        assert (tmp_path / "waylt_all_time_report.txt").exists()
        assert waylt_all_time.main([str(tmp_path / "missing.txt")]) == 1
        assert "Error:" in capsys.readouterr().err
