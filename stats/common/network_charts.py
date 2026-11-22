"""
The three taste-connection charts:

- the taste network: members as dots, joined by lines as thick as the number of songs they share,
  laid out so members with more in common sit closer together;
- the shared-songs map: members around a ring and the songs several of them picked in the middle, each
  song pulled toward the members who picked it;
- the overlap matrix: the exact number of shared songs for every pair.

Colours are the taste groups (blue, orange, aqua: the three hues that stay distinct for colour-blind
readers in any pairing), and every coloured mark is named, so colour is never the only cue.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import networkx as nx
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Rectangle

from stats.common.fonts import drawable, use_chart_fonts
from stats.common.network import MAX_GROUPS, Connections
from stats.common.plot import Box, ChartResult, LabelPlacer

GROUP_COLOURS = ("#2a78d6", "#eb6834", "#1baf7a")[:MAX_GROUPS]  # blue, orange, aqua
GROUP_NAMES = ("blue", "orange", "aqua")
OTHER_COLOUR = "#898781"  # members in no group, and songs picked across groups
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
EDGE_COLOUR = "#52514e"
EMPTY_CELL = "#f0efec"
GRID_COLOUR = "#e1e0d9"  # hairlines: the consensus target's rings
MUTED_INK = "#898781"  # ring labels
BLUE_RAMP = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")

LAYOUT_SEED = 7  # the force layout is randomised; a fixed seed draws the same chart every run
MIN_EDGE = 1  # the network draws pairs sharing at least this many songs (all pairs still shape the layout)
LABELLED_EDGES = 6  # the strongest links get their number written on them
MIN_PICKERS_ON_MAP = 3  # songs on at least this many lists appear on the shared-songs map
MATRIX_CELL = 0.5  # inches per member in the overlap matrix
MATRIX_SLANT = 55  # degrees the column names are turned
SONG_RADIUS = 0.8  # songs stay inside this circle; the members sit on the unit circle around them
SONG_DIAMETER_PER_LIST = 3.0  # points: a song on 7 lists is 21pt across, one on 3 lists 9pt
HEAVY_HITTER = 5  # songs on at least this many lists get their count inside the dot and a bold label
MAP_SIZE = (13, 12.5)  # inches
MAP_LIMITS = (1.45, 1.3)  # data units either side of the centre (the ring has radius 1)
TARGET_CENTRE = 0.22  # the consensus target: radius of a member sharing every song (the edge of the centre)
TARGET_SIZE = (12.5, 12)  # inches
TARGET_DOT = 130  # points², a member's dot on the target
AXES_SHARE = (0.94, 0.84)  # the share of the figure the chart area takes (see _figure)
# Points per data unit on the map (equal aspect, so the tighter of the two directions)
MAP_SCALE = 72 * min(MAP_SIZE[0] * AXES_SHARE[0] / (2 * MAP_LIMITS[0]),
                     MAP_SIZE[1] * AXES_SHARE[1] / (2 * MAP_LIMITS[1]))


def group_colour(connections: Connections, member: str) -> str:
    group = connections.group_of(member)
    return OTHER_COLOUR if group is None else GROUP_COLOURS[group]


def _figure(size: tuple[float, float]):
    use_chart_fonts()
    fig = Figure(figsize=size, dpi=100, facecolor=SURFACE)
    FigureCanvasAgg(fig)
    ax = fig.add_axes((0.03, 0.03, *AXES_SHARE))
    ax.set_facecolor(SURFACE)
    ax.set_axis_off()
    return fig, ax


def _titles(fig: Figure, title: str, subtitle: str):
    fig.text(0.03, 0.965, title, fontsize=15, fontweight="bold", color=INK, va="top")
    fig.text(0.03, 0.925, subtitle, fontsize=9, color=SECONDARY_INK, va="top", linespacing=1.5)


def song_size(lists: int) -> float:
    """A song dot's area in points² for a song on this many lists (its diameter grows with the count)."""
    return (SONG_DIAMETER_PER_LIST * lists) ** 2


def _legend(ax, connections: Connections, extra: Sequence[tuple[str, str]] = (), loc: str = "lower left"):
    """The taste groups ("Taste group 1", ...), then any extra (colour, label) entries."""
    handles = [Line2D([], [], marker="o", linestyle="", markersize=8, markerfacecolor=colour, markeredgecolor=SURFACE,
                      label=f"Taste group {i + 1}") for i, colour in enumerate(GROUP_COLOURS[:len(connections.groups)])]
    if connections.ungrouped:
        handles.append(Line2D([], [], marker="o", linestyle="", markersize=8, markerfacecolor=OTHER_COLOUR,
                              markeredgecolor=SURFACE, label="In no group"))
    handles += [Line2D([], [], marker="o", linestyle="", markersize=8, markerfacecolor=colour,
                       markeredgecolor=SURFACE, label=label) for colour, label in extra]
    return ax.legend(handles=handles, loc=loc, fontsize=8.5, frameon=False, labelcolor=SECONDARY_INK)


def _spread(pos: dict, movable: Sequence, min_distance: float, rounds: int = 300, radii: dict | None = None) -> dict:
    """
    Nudges movable nodes apart until none is within min_distance of another (deterministically). With
    radii (in data units), two nodes are also kept at least the sum of their radii apart.
    """
    pos = {node: [float(x), float(y)] for node, (x, y) in pos.items()}
    nodes = list(pos)
    for _ in range(rounds):
        moved = False
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
                distance = math.hypot(dx, dy)
                needed = max(min_distance, radii.get(a, 0) + radii.get(b, 0)) if radii else min_distance
                if distance >= needed:
                    continue
                if distance == 0:
                    dx, dy, distance = 1.0, 0.0, 1.0
                push = (needed - distance) / 2 + 1e-4
                ux, uy = dx / distance * push, dy / distance * push
                if a in movable:
                    pos[a][0] -= ux * (2 if b not in movable else 1)
                    pos[a][1] -= uy * (2 if b not in movable else 1)
                if b in movable:
                    pos[b][0] += ux * (2 if a not in movable else 1)
                    pos[b][1] += uy * (2 if a not in movable else 1)
                moved = True
        if not moved:
            break
    return {node: tuple(xy) for node, xy in pos.items()}


def _inside(xy: tuple[float, float], radius: float) -> tuple[float, float]:
    """The point, pulled in to the given radius if it's outside it (so songs stay clear of the members' names)."""
    distance = math.hypot(*xy)
    return xy if distance <= radius else (xy[0] * radius / distance, xy[1] * radius / distance)


def _frame(ax, pos: dict, margin: float):
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    ax.set_xlim(min(xs) - margin, max(xs) + margin)
    ax.set_ylim(min(ys) - margin, max(ys) + margin)


def _box(artist, renderer) -> Box:
    extent = artist.get_window_extent(renderer)
    return extent.x0, extent.y0, extent.x1, extent.y1


def _marker_boxes(ax, fig, points: Sequence[tuple[float, float]], sizes: Sequence[float]) -> list[Box]:
    boxes = []
    for (x, y), size in zip(points, sizes):
        px, py = ax.transData.transform((x, y))
        radius = math.sqrt(size) / 2 * fig.dpi / 72 + 1
        boxes.append((px - radius, py - radius, px + radius, py + radius))
    return boxes


def _area(ax) -> Box:
    return ax.bbox.x0 + 3, ax.bbox.y0 + 3, ax.bbox.x1 - 3, ax.bbox.y1 - 3


def taste_network(connections: Connections, *, title: str, path: Path) -> ChartResult:
    graph = connections.graph()
    pos = nx.spring_layout(graph, weight="weight", seed=LAYOUT_SEED, iterations=500)
    pos = _spread(pos, list(graph), min_distance=0.16)
    partners = {m: len(connections.partners(m)) for m in graph}
    sizes = {m: 50 + 22 * partners[m] for m in graph}

    fig, ax = _figure((12, 10))
    _titles(fig, title, "Each dot is a member (size scales with how many people they share a song with).\nLines "
                        f"join members who share {MIN_EDGE}+ songs (line thickness scales with # of shared songs).\n"
                        "Members with more in common are drawn closer together, and colours are taste groups.")
    edges = sorted(((a, b, d["weight"]) for a, b, d in graph.edges(data=True) if d["weight"] >= MIN_EDGE),
                   key=lambda edge: edge[2])
    strongest = max((w for _, _, w in edges), default=1)
    for a, b, weight in edges:
        ax.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]], color=EDGE_COLOUR, solid_capstyle="round",
                linewidth=0.4 + 4.6 * weight / strongest, alpha=0.18 + 0.5 * weight / strongest, zorder=1)
    members = list(graph)
    ax.scatter([pos[m][0] for m in members], [pos[m][1] for m in members], s=[sizes[m] for m in members],
               c=[group_colour(connections, m) for m in members], edgecolors=SURFACE, linewidths=2, zorder=3)
    _frame(ax, pos, margin=0.22)
    legend = _legend(ax, connections)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    obstacles = [_box(legend, renderer)]
    for a, b, weight in edges[::-1][:LABELLED_EDGES]:
        number = ax.text((pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2, str(weight), fontsize=8,
                         color=INK, ha="center", va="center", zorder=4,
                         bbox={"boxstyle": "round,pad=0.25", "facecolor": SURFACE, "edgecolor": "none"})
        x0, y0, x1, y1 = _box(number, renderer)
        obstacles.append((x0 - 4, y0 - 4, x1 + 4, y1 + 4))  # with its rounded background
    node_boxes = _marker_boxes(ax, fig, [pos[m] for m in members], [sizes[m] for m in members])
    placer = LabelPlacer(fig, ax, node_boxes + obstacles, [], _area(ax), fontsize=9, color=INK, halo=True)
    order = sorted(members, key=lambda m: -partners[m])
    labels = [placer.place(member, pos[member], clearance=math.sqrt(sizes[member]) / 2) for member in order]
    return _save(fig, path, labels, node_boxes, placer.crowded)


def shared_songs_map(connections: Connections, song_name: Callable[[object], str], *, title: str,
                     path: Path, min_pickers: int = MIN_PICKERS_ON_MAP) -> ChartResult:
    ring = [m for group in connections.groups for m in group + [None]] + connections.ungrouped  # None: a gap
    ring = ring[:-1] if ring and ring[-1] is None else ring
    pickers: dict = {}
    for member, songs in connections.lists.items():
        for song in songs:
            pickers.setdefault(song, []).append(member)
    songs = sorted((s for s, who in pickers.items() if len(who) >= min_pickers), key=lambda s: -len(pickers[s]))

    angles = {m: math.pi / 2 - 2 * math.pi * i / len(ring) for i, m in enumerate(ring) if m is not None}
    places = {m: (math.cos(angle), math.sin(angle)) for m, angle in angles.items()}  # clockwise from the top
    graph = nx.Graph()
    graph.add_nodes_from(places)
    for song in songs:
        graph.add_edges_from((("song", song), member) for member in pickers[song])
    start = {node: places.get(node, (0.0, 0.0)) for node in graph}
    pos = nx.spring_layout(graph, pos=start, fixed=list(places), seed=LAYOUT_SEED, iterations=300, k=0.18)
    song_nodes = [("song", s) for s in songs]
    song_sizes = [song_size(len(pickers[s])) for s in songs]
    # Room for each dot plus a few points, in data units
    radii = {n: (math.sqrt(size) / 2 + 6) / MAP_SCALE for n, size in zip(song_nodes, song_sizes)}
    for _ in range(10):  # apart from each other, and inside the ring, until both hold
        pos = _spread(pos, song_nodes, min_distance=0.06, radii=radii)
        pos = {node: _inside(xy, SONG_RADIUS) if node in song_nodes else xy for node, xy in pos.items()}

    def colour_of(song) -> str:
        groups = {connections.group_of(m) for m in pickers[song]}
        return GROUP_COLOURS[groups.pop()] if len(groups) == 1 and None not in groups else OTHER_COLOUR

    fig, ax = _figure(MAP_SIZE)
    _titles(fig, title, f"Members are around the ring, with every song on {min_pickers} or more lists in the\n"
                        f"middle (size scales with # of picks). Each song sits near the members who\n"
                        f"picked it. A song coloured like a taste group was picked only inside that group.")
    for song in songs:
        for member in pickers[song]:
            ax.plot([pos[("song", song)][0], places[member][0]], [pos[("song", song)][1], places[member][1]],
                    color=group_colour(connections, member), linewidth=0.7, alpha=0.22, zorder=1)
    ax.scatter([pos[n][0] for n in song_nodes], [pos[n][1] for n in song_nodes], s=song_sizes,
               c=[colour_of(s) for s in songs], edgecolors=SURFACE, linewidths=1.5, zorder=3)
    for song, node in zip(songs, song_nodes):  # the heavy hitters' counts, inside their dots
        if len(pickers[song]) >= HEAVY_HITTER:
            ax.text(*pos[node], str(len(pickers[song])), ha="center", va="center", fontsize=7.5, fontweight="bold",
                    color=_ink_on(colour_of(song)), zorder=4)
    members = list(places)
    ax.scatter([places[m][0] for m in members], [places[m][1] for m in members], s=150,
               c=[group_colour(connections, m) for m in members], edgecolors=SURFACE, linewidths=2, zorder=3)
    ax.set_xlim(-MAP_LIMITS[0], MAP_LIMITS[0])
    ax.set_ylim(-MAP_LIMITS[1], MAP_LIMITS[1])
    ax.set_aspect("equal")
    legend = _legend(ax, connections, [(OTHER_COLOUR, "Song picked across groups")], loc="upper right")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    obstacles = [_box(legend, renderer)]
    for member in members:  # names outside the ring, reading away from the centre
        x, y = places[member]
        name = ax.text(x * 1.07, y * 1.07, drawable(member), fontsize=9.5, color=INK, ha="left" if x > 0.05 else
                       "right" if x < -0.05 else "center", va="bottom" if y > 0.05 else "top" if y < -0.05 else
                       "center", zorder=4)
        obstacles.append(_box(name, renderer))
    dot_boxes = _marker_boxes(ax, fig, [pos[n] for n in song_nodes] + [places[m] for m in members],
                              song_sizes + [150] * len(members))
    placer = LabelPlacer(fig, ax, dot_boxes + obstacles, [], _area(ax), fontsize=7, color=INK, halo=True, gap=5)
    labels = [placer.place(song_name(s), pos[("song", s)], clearance=math.sqrt(size) / 2,
                           emphasis=_song_label_style(len(pickers[s]))) for s, size in zip(songs, song_sizes)]
    return _save(fig, path, labels, dot_boxes, placer.crowded)


def target_radius(shared: int, top_n: int) -> float:
    """How far from the centre a member sharing this many of the top_n songs sits: 0 shared is the outer ring."""
    return TARGET_CENTRE + (1 - TARGET_CENTRE) * (top_n - shared) / top_n


def ring_step(top_n: int) -> int:
    """Shared-song counts between the rings: about five rings whatever the list length (5 for 25, 3 for 15)."""
    return max(1, round(top_n / 5))


def _target_angles(connections: Connections, shared: Mapping[str, int]) -> dict[str, float]:
    """
    Each member's angle in radians, clockwise from the top: a slice of the circle per taste group (closest
    to the community first within it), a gap between groups, and an empty slot at the top for the ring labels.
    """
    segments = [sorted(group, key=lambda m: (-shared[m], m.casefold())) for group in connections.groups]
    if connections.ungrouped:
        segments.append(sorted(connections.ungrouped, key=lambda m: (-shared[m], m.casefold())))
    slots = sum(len(segment) for segment in segments) + len(segments)  # one gap after each segment
    step = 2 * math.pi / slots
    angles, slot = {}, 0.5  # half a slot in, so the label gap is centred on the top
    for segment in segments:
        for member in segment:
            angles[member] = math.pi / 2 - (slot + 0.5) * step
            slot += 1
        slot += 1
    return angles


def consensus_target(connections: Connections, shared: Mapping[str, int], top_n: int, *, title: str,
                     path: Path) -> ChartResult:
    """
    The community's Top N in the middle, and each member at a distance from it set by how many of their
    ranked picks made it: the more they share, the closer in.
    """
    angles = _target_angles(connections, shared)
    members = list(angles)
    places = {m: (target_radius(shared[m], top_n) * math.cos(angles[m]),
                  target_radius(shared[m], top_n) * math.sin(angles[m])) for m in members}
    step = ring_step(top_n)
    rings = list(range(0, top_n, step))  # 0 is the outer ring; top_n itself is the centre's edge

    fig, ax = _figure(TARGET_SIZE)
    _titles(fig, title, f"Each member is a dot: the closer to the centre, the more of their {top_n} ranked picks made "
                        f"the community Top {top_n}.\nRings mark every {step} songs shared. Colours are taste groups.")
    for k in rings:
        ax.add_patch(Circle((0, 0), target_radius(k, top_n), fill=False, edgecolor=GRID_COLOUR, linewidth=0.8,
                            zorder=0))
    hub = TARGET_CENTRE * 0.82
    ax.add_patch(Circle((0, 0), hub, facecolor=INK, edgecolor="none", zorder=2))
    spokes = []
    for member in members:
        start = (hub * math.cos(angles[member]), hub * math.sin(angles[member]))
        ax.plot([start[0], places[member][0]], [start[1], places[member][1]], color=group_colour(connections, member),
                linewidth=1.2, alpha=0.35, solid_capstyle="round", zorder=1)
        spokes.append((start, places[member]))
    ax.scatter([places[m][0] for m in members], [places[m][1] for m in members], s=TARGET_DOT,
               c=[group_colour(connections, m) for m in members], edgecolors=SURFACE, linewidths=2, zorder=3)
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-1.15, 1.15)
    ax.set_aspect("equal")
    centre_label = ax.text(0, 0, f"Community\nTop {top_n}", ha="center", va="center", fontsize=10, fontweight="bold",
                           color=SURFACE, zorder=4, linespacing=1.3)
    ring_labels = [ax.text(0, target_radius(k, top_n), f"{k} shared" if k else "0", ha="center", va="center",
                           fontsize=8, color=MUTED_INK, zorder=4,
                           bbox={"boxstyle": "round,pad=0.2", "facecolor": SURFACE, "edgecolor": "none"})
                   for k in rings]
    legend = _legend(ax, connections, loc="upper right")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    obstacles = [_box(artist, renderer) for artist in (legend, centre_label, *ring_labels)]
    centre_px = ax.transData.transform((0, 0))
    hub_px = ax.transData.transform((hub, 0))[0] - centre_px[0]
    obstacles.append((centre_px[0] - hub_px, centre_px[1] - hub_px, centre_px[0] + hub_px, centre_px[1] + hub_px))
    dot_boxes = _marker_boxes(ax, fig, [places[m] for m in members], [TARGET_DOT] * len(members))
    pixel_spokes = [tuple(tuple(ax.transData.transform(point)) for point in spoke) for spoke in spokes]
    placer = LabelPlacer(fig, ax, dot_boxes + obstacles, pixel_spokes, _area(ax), fontsize=9, color=INK, halo=True,
                         gap=3)
    order = sorted(members, key=lambda m: (-shared[m], m.casefold()))  # the closest get the nearest spots
    labels = [placer.place(f"{member} ({shared[member]})", places[member], clearance=math.sqrt(TARGET_DOT) / 2)
              for member in order]
    return _save(fig, path, labels, dot_boxes, placer.crowded)


def _song_label_style(lists: int) -> dict:
    """Bigger, bold labels for the songs on the most lists."""
    if lists >= HEAVY_HITTER:
        return {"fontsize": 8.5, "fontweight": "bold"}
    return {"fontsize": 7.5} if lists > MIN_PICKERS_ON_MAP else {}


def _text_width(texts: Sequence[str], fontsize: float) -> float:
    """The widest of the texts, in inches, as the charts draw them."""
    fig = Figure(dpi=100)
    FigureCanvasAgg(fig)
    renderer = fig.canvas.get_renderer()
    return max((fig.text(0, 0, text, fontsize=fontsize).get_window_extent(renderer).width / fig.dpi
                for text in texts), default=0.0)


def _ramp_colour(value: int, top: int) -> str:
    """The blue ramp's step for value (1..top); the lightest step is 1 shared song."""
    if top <= 1:
        return BLUE_RAMP[0]
    return LinearSegmentedColormap.from_list("ramp", BLUE_RAMP)((value - 1) / (top - 1))


def _ink_on(colour) -> str:
    r, g, b = to_rgb(colour)
    return "#ffffff" if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.45 else INK


def overlap_matrix(connections: Connections, *, title: str, path: Path) -> Path:
    order = [m for group in connections.groups for m in group] + connections.ungrouped
    breaks = set()  # positions where a new group starts get a gap
    position = 0
    for group in connections.groups:
        position += len(group)
        breaks.add(position)
    gap = 0.35
    coords = []
    offset = 0.0
    for i, _ in enumerate(order):
        if i in breaks:
            offset += gap
        coords.append(i + offset)
    top = max((len(songs) for songs in connections.shared.values()), default=1)
    names = [drawable(m) for m in order]

    # Laid out in inches around the longest name, so the slanted column names fit under the subtitle
    # and the last one doesn't run off the right edge
    use_chart_fonts()
    name = _text_width(names, fontsize=9)
    span = coords[-1] + 1.1  # data units across the grid
    grid = span * MATRIX_CELL
    slant = math.radians(MATRIX_SLANT)
    left = name + 0.85  # the name, the gap (tick pad) and the group swatch
    right = max(0.3, name * math.cos(slant) - 0.25)
    above = name * math.sin(slant) + 0.75
    header, below = 1.15, 0.3
    width, height = left + grid + right, header + above + grid + below
    fig = Figure(figsize=(width, height), dpi=100, facecolor=SURFACE)
    FigureCanvasAgg(fig)
    ax = fig.add_axes((left / width, below / height, grid / width, grid / height))
    ax.set_facecolor(SURFACE)
    _titles(fig, title, "How many songs each pair both picked (darker means more in common).\n"
                        "Members are grouped by taste.")
    for row, a in enumerate(order):
        for col, b in enumerate(order):
            x, y = coords[col], coords[row]
            if a == b:
                continue
            count = connections.count(a, b)
            colour = _ramp_colour(count, top) if count else EMPTY_CELL
            ax.add_patch(Rectangle((x + 0.04, y + 0.04), 0.92, 0.92, facecolor=colour, edgecolor="none"))
            if count:
                ax.text(x + 0.5, y + 0.5, str(count), ha="center", va="center", fontsize=8.5, color=_ink_on(colour))
    ticks = [c + 0.5 for c in coords]
    ax.set_xticks(ticks, names, rotation=MATRIX_SLANT, ha="left", rotation_mode="anchor", fontsize=9, color=INK)
    ax.set_yticks(ticks, names, fontsize=9, color=INK)
    ax.xaxis.tick_top()
    ax.tick_params(length=0, pad=30)  # clear of the group swatches
    for i, member in enumerate(order):  # a group swatch beside each name
        colour = group_colour(connections, member)
        ax.add_patch(Rectangle((-0.62, coords[i] + 0.3), 0.4, 0.4, facecolor=colour, edgecolor="none", clip_on=False))
        ax.add_patch(Rectangle((coords[i] + 0.3, -0.62), 0.4, 0.4, facecolor=colour, edgecolor="none", clip_on=False))
    ax.set_xlim(-0.05, coords[-1] + 1.05)
    ax.set_ylim(coords[-1] + 1.05, -0.05)
    ax.set_aspect("equal")
    for spine in ax.spines.values():
        spine.set_visible(False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    return path


def _save(fig: Figure, path: Path, labels: list[Box], dots: list[Box], crowded: list[str]) -> ChartResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    return ChartResult(path, labels, dots, crowded)
