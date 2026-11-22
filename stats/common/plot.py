"""
The picks-vs-points scatter chart for the Top 15 So Far and the end of year Top 100.

Labels are placed deterministically rather than by a physics simulation (adjustText): each label is
measured with the real renderer and tried at positions around its dot, nearest first, in rings of
increasing distance. It takes the first spot that stays inside the chart and doesn't touch any dot,
another label, a leader line, the legend or the cutoff note. A label more than a few points from its
dot gets a thin leader line. The same data always gives the same chart.
"""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

PINK = "#ff4980"
LIGHT_PINK = "#ffb3c8"
CUTOFF_COLOUR = "#b48fc1"  # a darker thistle, readable on white
TREND_COLOUR = "#7d9bc9"  # a darker lightsteelblue
TEXT_COLOUR = "#333333"
LEADER_COLOUR = "#9a9a9a"

MARKER_AREA = 30  # points², matplotlib's `s`
MARKER_RADIUS = math.sqrt(MARKER_AREA) / 2  # points
FONT_SIZE = 6.5
MAX_LABEL_LENGTH = 34
SAME_SPOT_STEP = 0.09  # x distance between dots for songs on the same picks and points
SAME_SPOT_WIDTH = 0.5  # the most x room a group of identical dots spreads over
LEADER_FROM = 9  # points: labels further than this from their dot get a leader line
# Only a label right beside its dot (centred on it) is unmistakable without a leader line; above or below,
# in a dense column, it could belong to the next dot
BESIDE = (0, 180)
RINGS = (6, 10, 16, 24, 34, 46, 60, 76, 94, 115, 140)  # points from the dot
# Directions tried in each ring, as angles in degrees: beside the dot first, then diagonals, then above/below
DIRECTIONS = (0, 180, 30, -30, 150, -150, 60, -60, 120, -120, 90, -90, 15, -15, 165, -165, 45, -45, 135, -135)

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in display pixels


@dataclass(frozen=True)
class Dot:
    """One song on the chart."""
    picks: int
    points: int
    label: str | None = None  # None: drawn without a label
    made_cut: bool = False


@dataclass(frozen=True)
class ChartResult:
    """The saved chart, and where things landed on it."""
    path: Path
    label_boxes: list[Box]  # where each label landed, in display pixels (for checking overlaps)
    dot_boxes: list[Box]
    crowded: list[str]  # labels that found no clear spot (placed where they overlap least)


def _overlaps(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _overlap_area(a: Box, b: Box) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _segment_hits(start: tuple[float, float], end: tuple[float, float], box: Box) -> bool:
    """Whether the line segment passes through the box (Liang–Barsky clipping)."""
    (x0, y0), (x1, y1) = start, end
    dx, dy = x1 - x0, y1 - y0
    low, high = 0.0, 1.0
    for p, q in ((-dx, x0 - box[0]), (dx, box[2] - x0), (-dy, y0 - box[1]), (dy, box[3] - y0)):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            low = max(low, t)
        else:
            high = min(high, t)
        if low > high:
            return False
    return True


def _grow(box: Box, pixels: float) -> Box:
    return box[0] - pixels, box[1] - pixels, box[2] + pixels, box[3] + pixels


def spread_same_spots(dots: Sequence[Dot]) -> list[float]:
    """Each dot's x: its picks, nudged sideways (evenly, not randomly) when several share a spot."""
    groups = defaultdict(list)
    for index, dot in enumerate(dots):
        groups[(dot.picks, dot.points)].append(index)
    xs = [float(dot.picks) for dot in dots]
    for members in groups.values():
        step = min(SAME_SPOT_STEP, SAME_SPOT_WIDTH / len(members))
        for position, index in enumerate(members):
            xs[index] += (position - (len(members) - 1) / 2) * step
    return xs


def trend_line(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float] | None:
    """Least-squares (slope, intercept), or None when every x is the same."""
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    spread = sum((x - mean_x) ** 2 for x in xs)
    if spread == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread
    return slope, mean_y - slope * mean_x


def _alignment(angle: float) -> tuple[str, str, tuple[float, float]]:
    """Text alignment that grows the label away from its dot, and the leader line's end on the label."""
    dx, dy = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    ha = "left" if dx > 0.4 else "right" if dx < -0.4 else "center"
    va = "bottom" if dy > 0.4 else "top" if dy < -0.4 else "center"
    relpos = ({"left": 0.0, "right": 1.0, "center": 0.5}[ha], {"bottom": 0.0, "top": 1.0, "center": 0.5}[va])
    return ha, va, relpos


def _shorten(label: str) -> str:
    return label if len(label) <= MAX_LABEL_LENGTH else label[:MAX_LABEL_LENGTH - 1].rstrip() + "…"


class _LabelPlacer:
    """Finds each label a clear spot, in the order labels are placed (the first get the closest spots)."""

    def __init__(self, fig: Figure, ax, obstacles: list[Box], lines: list, area: Box):
        self.fig, self.ax = fig, ax
        self.renderer = fig.canvas.get_renderer()
        self.obstacles = obstacles
        self.lines = lines  # the trend and cutoff lines, which labels shouldn't sit on
        self.area = area
        self.taken: list[Box] = []
        self.leaders: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self.crowded: list[str] = []

    def _measure(self, text: str, xy: tuple[float, float], radius: float, angle: float):
        ha, va, relpos = _alignment(angle)
        offset = (radius * math.cos(math.radians(angle)), radius * math.sin(math.radians(angle)))
        probe = self.ax.annotate(text, xy, xytext=offset, textcoords="offset points", fontsize=FONT_SIZE,
                                 ha=ha, va=va)
        extent = probe.get_window_extent(self.renderer)
        probe.remove()
        box = (extent.x0, extent.y0, extent.x1, extent.y1)
        anchor = self.ax.transData.transform(xy)
        end = (box[0] + relpos[0] * (box[2] - box[0]), box[1] + relpos[1] * (box[3] - box[1]))
        return box, (tuple(anchor), end), (ha, va, relpos, offset)

    def _cost(self, box: Box, leader, needs_leader: bool) -> float:
        """0 for a clear spot; otherwise how much it overlaps."""
        cost = 0.0
        if not (box[0] >= self.area[0] and box[1] >= self.area[1]
                and box[2] <= self.area[2] and box[3] <= self.area[3]):
            cost += 1e6
        padded = _grow(box, 1.5)
        cost += sum(_overlap_area(padded, other) + 50 for other in self.obstacles if _overlaps(padded, other))
        cost += sum(_overlap_area(padded, other) + 200 for other in self.taken if _overlaps(padded, other))
        cost += sum(100 for start, end in self.leaders if _segment_hits(start, end, padded))
        cost += sum(60 for start, end in self.lines if _segment_hits(start, end, padded))
        if needs_leader:
            cost += sum(100 for other in self.taken if _segment_hits(*leader, other))
        return cost

    def place(self, text: str, xy: tuple[float, float]) -> Box:
        options = []  # nearest first, up to the first clear spot
        for radius, angle in ((r, a) for r in RINGS for a in DIRECTIONS if r > LEADER_FROM or a in BESIDE):
            box, leader, style = self._measure(text, xy, radius, angle)
            options.append((self._cost(box, leader, radius > LEADER_FROM), radius, box, leader, style))
            if options[-1][0] == 0:
                break
        cost, radius, box, leader, (ha, va, relpos, offset) = min(options, key=lambda option: option[0])
        if cost:
            self.crowded.append(text)
        arrow = None
        if radius > LEADER_FROM:
            arrow = {"arrowstyle": "-", "color": LEADER_COLOUR, "lw": 0.5, "shrinkA": 0,
                     "shrinkB": MARKER_RADIUS + 0.5, "relpos": relpos}
            self.leaders.append(leader)
        self.ax.annotate(text, xy, xytext=offset, textcoords="offset points", fontsize=FONT_SIZE, ha=ha, va=va,
                         color=TEXT_COLOUR, arrowprops=arrow, zorder=5)
        self.taken.append(box)
        return box


def scatter_chart(dots: Sequence[Dot], *, title: str, cutoff_points: int | None, cutoff_label: str,
                  path: Path) -> ChartResult:
    """Draws the chart and saves it as a PNG at path."""
    xs = spread_same_spots(dots)
    ys = [dot.points for dot in dots]
    max_picks, max_points = max(dot.picks for dot in dots), max(ys)

    fig = Figure(figsize=(13, 8), dpi=100)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot()
    made, missed = [i for i, d in enumerate(dots) if d.made_cut], [i for i, d in enumerate(dots) if not d.made_cut]
    ax.scatter([xs[i] for i in missed], [ys[i] for i in missed], s=MARKER_AREA, color=LIGHT_PINK,
               edgecolors="none", label="Other songs", zorder=3)
    ax.scatter([xs[i] for i in made], [ys[i] for i in made], s=MARKER_AREA, color=PINK, edgecolors="none",
               label=cutoff_label, zorder=4)

    lines = []  # in data coordinates, converted to pixels once the layout is fixed
    trend = trend_line([float(d.picks) for d in dots], ys)
    if trend:
        slope, intercept = trend
        ends = [(0.5, slope * 0.5 + intercept), (max_picks + 0.5, slope * (max_picks + 0.5) + intercept)]
        ax.plot(*zip(*ends), color=TREND_COLOUR, linestyle="--", linewidth=1, alpha=0.8, zorder=2,
                label=f"Trend (y = {slope:.2f}x {'+' if intercept >= 0 else '−'} {abs(intercept):.2f})")
        lines.append(ends)
    cutoff_note = None
    if cutoff_points is not None:
        ax.axhline(cutoff_points, color=CUTOFF_COLOUR, linestyle="--", linewidth=1.2, zorder=1)
        lines.append([(0.4, cutoff_points), (max_picks + 0.9, cutoff_points)])
        cutoff_note = ax.text(max_picks + 0.85, cutoff_points + max_points * 0.008,
                              f"{cutoff_label} cutoff ({cutoff_points} pts)", color=CUTOFF_COLOUR, fontsize=7.5,
                              style="italic", ha="right", va="bottom")

    ax.set_title(title, fontsize=13, fontweight="bold", pad=14)
    ax.set_xlabel("Number of picks", fontsize=10, labelpad=8)
    ax.set_ylabel("Total points", fontsize=10, labelpad=8)
    ax.set_xlim(0.4, max_picks + 0.9)
    ax.set_ylim(-max_points * 0.03, max_points * 1.1 + 2)
    ax.set_xticks(range(1, max_picks + 1))
    ax.grid(True, linestyle=":", alpha=0.5, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    legend = ax.legend(loc="upper left", fontsize=8, frameon=True)
    fig.tight_layout()
    fig.canvas.draw()  # fixes the layout, so the label positions measured below are final

    to_pixels = ax.transData.transform
    radius = MARKER_RADIUS * fig.dpi / 72
    dot_boxes = [(px - radius, py - radius, px + radius, py + radius)
                 for px, py in (to_pixels((x, y)) for x, y in zip(xs, ys))]
    obstacles = list(dot_boxes)
    for artist in (legend, cutoff_note):
        if artist is not None:
            extent = artist.get_window_extent(fig.canvas.get_renderer())
            obstacles.append((extent.x0, extent.y0, extent.x1, extent.y1))
    area = _grow((ax.bbox.x0, ax.bbox.y0, ax.bbox.x1, ax.bbox.y1), -3)

    pixel_lines = [tuple(tuple(to_pixels(point)) for point in line) for line in lines]
    placer = _LabelPlacer(fig, ax, obstacles, pixel_lines, area)
    labelled = sorted((i for i, dot in enumerate(dots) if dot.label), key=lambda i: (-ys[i], -dots[i].picks))
    label_boxes = [placer.place(_shorten(dots[i].label), (xs[i], ys[i])) for i in labelled]

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300)
    return ChartResult(path, label_boxes, dot_boxes, placer.crowded)
