# Stats

Fun stats for the community list videos, made from the files IU exports. Nothing here runs in the bot
or ships in the Docker image; the charts need matplotlib, which is in the `dev` group (`uv sync`).

Run everything from the repo root. Each report is printed and saved in `stats/output/` (git-ignored),
with the chart for the Top 100 and the Top 15 So Far.

| Video | Get the file with | Run |
| --- | --- | --- |
| End of year Top 100 | `/export-end-of-year-nominations` → `top_25_<year>.txt` | `uv run python -m stats.ranked_lists top_100 stats/data/top_100/top_25_2025.txt` |
| Top 15 So Far (mid-year) | `/export-lists <event_id>` → `<event_id>_stats.txt` | `uv run python -m stats.ranked_lists mid_year stats/data/mid_year/mid_year_2026_stats.txt` |
| All-Time Top 15 | `/export-lists <event_id>` | `uv run python -m stats.ranked_lists all_time stats/data/all_time/all_time_2026_stats.txt` |
| What Are You Listening To | `/export-lists <event_id>` | `uv run python -m stats.waylt stats/data/waylt/waylt_2026_10_stats.txt` |
| What Are You Listening To, all time | the old spreadsheet (`.csv`) and/or every `/export-lists` file, oldest first | `uv run python -m stats.waylt_all_time Picks.csv stats/data/waylt/*_stats.txt` |

The HMA and Hall of Fame results come from `/end-of-year-results` in Discord.

## Input format

Both export commands write each member's list under a `--- username ---` header, numbered, with a blank
line between lists:

```text
--- HallyU ---
1. KiiiKiii // Pop Off Pop Off
2. Odd Youth // can't go back

--- AdamShorts ---
1. Ateez // Bad
```

A file that isn't laid out like this (a pick before any header, a member twice, numbering that skips,
or the wrong number of picks for the video) is refused with every problem listed. IU accepts a pick
without `//` rather than make members retype their list; the stats count it as a song with no artist
and list it under **Data notes**. The `_urls.txt` files are the link sheets for editing the video;
the stats don't read them.

`stats/data/` holds an example of each export. The all-time file's member names are placeholders.

## How it counts

- **Points:** 1st place is worth as many points as there are ranked picks (25 for the Top 25, 15 for
  the Top 15), down to 1 for last. The mid-year honourable mention scores nothing but counts as a pick.
- **Ties** in a points ranking go to the most #1 picks, then the most picks, then a random draw. Drawn
  places are marked `*`, and the report gives the seed: `--seed N` repeats the same draw. If the draw
  decides who makes the video (the Top 100 or Top 15 cutoff), **Data notes** says so and names the songs.
- **The All-Time Top 15 ranks artists**, since few songs repeat on all-time lists.
- **Names** are matched however they were typed: capitals, spacing, punctuation, curly quotes,
  `feat.` credits, a trailing `(Eng. Ver.)` and nicknames (`SKZ`, `i-dle`, ...). Each is shown in its
  most common spelling. Spellings merged beyond capitals are listed under **Data notes**; add new
  nicknames to `ARTIST_ALIASES` in `common/normalize.py`.
- **Closest lists** compares each pair of members by the share of songs in common, and again weighting
  each shared song by how close the two lists placed it.
- **Chains** (What Are You Listening To) link members whose lists share a song, each by a different
  song, to give the video an order. The search tries every arrangement, which is quick for the ~20
  lists a video gets.

## Code

| Module | What it does |
| --- | --- |
| `ranked_lists.py` | The Top 100, Top 15 So Far and All-Time Top 15 reports. `FORMATS` sets each video's picks, honourable mentions, cutoff and chart |
| `waylt.py`, `waylt_all_time.py` | The What Are You Listening To reports |
| `common/parsing.py` | Reads the export files |
| `common/normalize.py` | Matches names; `ARTIST_ALIASES` |
| `common/tally.py` | Counts points, picks and #1s; ranks with the tiebreaks |
| `common/sections.py` | The sections every report shares (most picked songs and artists, data notes) |
| `common/similarity.py`, `common/chains.py` | Closest lists; chains |
| `common/report.py` | Lays out the text report (aligned for Hangul and emoji) |
| `common/plot.py` | The scatter chart. Labels are placed deterministically: each is measured and tried around its dot, nearest first, until it is clear of every dot, label, line and the legend. A label not right beside its dot gets a leader line |

Tests are in `tests/stats/`, and pylint covers this folder (`uv run pylint iu tests stats`).
