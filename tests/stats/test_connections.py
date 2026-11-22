"""The taste connections report and its three charts."""

from pathlib import Path

import pytest
from matplotlib.image import imread
from testsupport.stats_lists import export, table_rows

from stats.common.network import connect
from stats.common.network_charts import (_inside, _ink_on, _ramp_colour, _song_label_style, _spread, overlap_matrix,
                                         shared_songs_map, song_size, taste_network)
from stats.connections import build_report, main

SAMPLE = Path(__file__).resolve().parents[2] / "stats" / "data" / "top_100" / "top_25_2025.txt"
MID_YEAR_SAMPLE = SAMPLE.parents[1] / "mid_year" / "mid_year_2026_stats.txt"


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@pytest.fixture(name="sample_report", scope="module")
def make_sample_report(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    return build_report("top_100", SAMPLE, out).text(), out


def test_the_sample_report_has_every_section(sample_report):
    text, _ = sample_report

    assert text.startswith("TASTE CONNECTIONS: TOP 25 SONGS OF 2025")
    assert "15 members, 105 pairs: 80 pairs share at least one song, 25 share none" in text
    for title in ("Taste groups", "Songs that bridge the groups", "Strongest connections",
                  "Each member's connections", "Charts", "Data notes"):
        assert f"\n{title}\n" in text
    assert "Couldn't find a clear spot" not in text


def test_the_strongest_pair_comes_first(sample_report):
    text, _ = sample_report

    rows = table_rows(text.split("\nStrongest connections\n", 1)[1])
    assert rows[4][:2] == ["Diana4Dragons ↔ Alexrandia", "12"]


def test_the_sample_charts_are_saved(sample_report):
    _, out = sample_report

    for chart in ("taste_network", "shared_songs_map", "overlap_matrix"):
        assert (out / f"top_25_2025_{chart}.png").read_bytes().startswith(b"\x89PNG")


def test_the_mid_year_sample_works_too(tmp_path):
    # 15 ranked picks plus an honourable mention, and a member name with emoji the charts can't draw
    text = build_report("mid_year", MID_YEAR_SAMPLE, tmp_path).text()

    assert text.startswith("TASTE CONNECTIONS: TOP 15 SONGS OF 2026 SO FAR")
    assert "14 members, 91 pairs" in text
    assert "Couldn't find a clear spot" not in text
    for chart in ("taste_network", "shared_songs_map", "overlap_matrix"):
        assert (tmp_path / f"mid_year_2026_stats_{chart}.png").read_bytes().startswith(b"\x89PNG")


def test_the_matrix_widens_for_long_names(tmp_path):
    def width(name):
        connections = connect({"a": ["1", "2"], name: ["1", "3"], "c": ["2", "3"]})
        path = overlap_matrix(connections, title="T", path=tmp_path / f"{len(name)}.png")
        return imread(path).shape[1]

    assert width("a much, much longer member name than usual") > width("b")


def test_labels_are_clear_of_each_other_and_the_dots(tmp_path):
    lists = {f"m{i}": [f"s{(i * 3 + j) % 30}" for j in range(10)] for i in range(12)}
    connections = connect(lists)

    for result in (taste_network(connections, title="T", path=tmp_path / "net.png"),
                   shared_songs_map(connections, str, title="T", path=tmp_path / "map.png")):
        boxes = result.label_boxes
        assert not result.crowded
        assert not any(_overlap(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:])
        assert not any(_overlap(label, dot) for label in boxes for dot in result.dot_boxes)


def test_charts_for_members_who_share_nothing(tmp_path):
    connections = connect({"a": ["1"], "b": ["2"]})

    assert taste_network(connections, title="T", path=tmp_path / "n.png").path.exists()
    assert not shared_songs_map(connections, str, title="T", path=tmp_path / "m.png").label_boxes
    assert overlap_matrix(connections, title="T", path=tmp_path / "x.png").exists()


def test_a_report_for_a_small_file(list_file, tmp_path):
    lists = [(name, [f"A{(i + n) % 30} // S{(i + n) % 30}" for i in range(25)]) for n, name in enumerate("JSABC")]
    lists.append(("Loner", [f"L{i} // Only Mine {i}" for i in range(25)]))
    path = list_file(export(*lists), name="top_25_2026.txt")

    text = build_report("top_100", path, tmp_path).text()

    assert "6 members, 15 pairs" in text
    assert "In no group: Loner" in text
    # Neighbouring lists share 24 songs; level pairs are listed by name
    assert table_rows(text.split("\nStrongest connections\n", 1)[1])[4][:2] == ["A ↔ B", "24"]


def test_a_report_where_nobody_shares_a_song(list_file, tmp_path):
    path = list_file(export(*((name, [f"{name} // Song {i}" for i in range(25)]) for name in "JS")))

    text = build_report("top_100", path, tmp_path).text()

    assert "No groups: nobody shares a song." in text
    assert "2 members, 1 pairs: 0 pairs share at least one song, 1 share none" in text


def test_spread_keeps_nodes_apart_and_leaves_fixed_ones():
    pos = _spread({"a": (0.0, 0.0), "b": (0.0, 0.0), "fixed": (0.05, 0.0)}, ["a", "b"], min_distance=0.1)

    assert pos["fixed"] == (0.05, 0.0)
    assert abs(pos["a"][0] - pos["b"][0]) + abs(pos["a"][1] - pos["b"][1]) >= 0.099


def test_inside_pulls_a_point_onto_the_circle():
    assert _inside((0.3, 0.4), 1.0) == (0.3, 0.4)
    assert _inside((3.0, 4.0), 1.0) == pytest.approx((0.6, 0.8))


def test_the_ramp_runs_light_to_dark_and_text_stays_readable():
    assert _ramp_colour(1, 1) == "#cde2fb"
    light, dark = _ramp_colour(1, 10), _ramp_colour(10, 10)
    assert sum(light[:3]) > sum(dark[:3])
    assert _ink_on(light) == "#0b0b0b"
    assert _ink_on(dark) == "#ffffff"


def test_main(tmp_path, capsys):
    assert main(["top_100", str(SAMPLE), "--out-dir", str(tmp_path)]) == 0
    assert (tmp_path / "top_25_2025_connections_report.txt").exists()
    assert main(["top_100", str(tmp_path / "missing.txt")]) == 1
    assert "Error:" in capsys.readouterr().err


def test_bigger_songs_grow_fast_and_get_bolder_labels():
    assert song_size(7) / song_size(3) == pytest.approx((7 / 3) ** 2)  # the diameter grows with the count
    assert not _song_label_style(3)
    assert _song_label_style(4) == {"fontsize": 7.5}
    assert _song_label_style(5) == {"fontsize": 8.5, "fontweight": "bold"}


def test_spread_keeps_big_dots_their_own_room():
    pos = _spread({"big": (0.0, 0.0), "small": (0.01, 0.0)}, ["big", "small"], min_distance=0.01,
                  radii={"big": 0.1, "small": 0.02})

    assert abs(pos["big"][0] - pos["small"][0]) >= 0.119
