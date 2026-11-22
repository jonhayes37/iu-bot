"""The picks-vs-points chart and its label placement."""

import pytest

from stats.common.plot import Dot, _segment_hits, scatter_chart, spread_same_spots, trend_line


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_dots_on_the_same_spot_are_spread_evenly():
    xs = spread_same_spots([Dot(2, 10), Dot(2, 10), Dot(2, 10), Dot(3, 10)])

    assert xs[0] < xs[1] < xs[2]
    assert xs[1] == pytest.approx(2.0)
    assert xs[2] - xs[1] == pytest.approx(xs[1] - xs[0])
    assert xs[3] == 3.0


def test_a_big_group_stays_within_its_column():
    xs = spread_same_spots([Dot(1, 5)] * 40)

    assert max(xs) - min(xs) <= 0.5


def test_trend_line():
    assert trend_line([1, 2, 3], [2, 4, 6]) == pytest.approx((2.0, 0.0))
    assert trend_line([2, 2], [1, 5]) is None


@pytest.mark.parametrize("start, end, hits", [
    ((0, 5), (20, 5), True),  # straight through
    ((0, 0), (1.5, 1.5), False),  # stops short
    ((0, 20), (20, 20), False),  # passes above
    ((5, 0), (5, 20), True),  # vertical, through
    ((20, 0), (20, 20), False),  # vertical, beside
])
def test_segment_hits(start, end, hits):
    assert _segment_hits(start, end, (2, 2, 10, 10)) is hits


def test_labels_land_clear_of_each_other_and_of_every_dot(tmp_path):
    # Like a real chart: a dense cloud of low scorers, and labelled songs close together above it
    dots = [Dot(1 + i % 3, (i * 7) % 15 * (1 + i % 3), None) for i in range(120)]
    dots += [Dot(2 + i % 4, 30 + i * 2, f"Artist {i} – A Song Title {i}", True) for i in range(16)]
    dots += [Dot(6, 90, "IVE – Bang Bang", True), Dot(6, 89, "Billlie – Work", True)]

    result = scatter_chart(dots, title="Test", cutoff_points=30, cutoff_label="Top 20",
                           path=tmp_path / "chart.png")

    assert result.path.read_bytes().startswith(b"\x89PNG")
    assert not result.crowded
    boxes = result.label_boxes
    assert len(boxes) == 18
    assert not any(_overlap(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:])
    assert not any(_overlap(label, dot) for label in boxes for dot in result.dot_boxes)


def test_a_chart_with_one_column_and_no_cutoff(tmp_path):
    result = scatter_chart([Dot(1, 5, "A – a"), Dot(1, 3)], title="T", cutoff_points=None, cutoff_label="Top 15",
                           path=tmp_path / "chart.png")

    assert result.path.exists()
    assert len(result.label_boxes) == 1


def test_a_label_with_no_clear_spot_is_reported(tmp_path, monkeypatch):
    # Only one spot to try, right beside the dot, and the song next to it is in the way
    monkeypatch.setattr("stats.common.plot.RINGS", (6,))
    monkeypatch.setattr("stats.common.plot.DIRECTIONS", (0,))
    dots = [Dot(1, 10, "Buried – Song"), Dot(1, 10), Dot(2, 3)]

    result = scatter_chart(dots, title="T", cutoff_points=None, cutoff_label="Top 15", path=tmp_path / "c.png")

    assert result.crowded == ["Buried – Song"]
