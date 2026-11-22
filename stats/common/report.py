"""Plain-text reports: one title, then sections of tables, laid out the same way by every script."""

import unicodedata
from collections.abc import Sequence
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def display_width(text: str) -> int:
    """Columns a terminal gives the text: Hangul, CJK and emoji take two, combining marks none."""
    width = 0
    for char in text:
        if unicodedata.combining(char) or char in "‍︎️":
            continue
        width += 2 if unicodedata.east_asian_width(char) in "WF" else 1
    return width


def _pad(text: str, width: int, right: bool) -> str:
    padding = " " * (width - display_width(text))
    return padding + text if right else text + padding


class Report:
    """Collects a report's lines; `text()` gives the whole report."""

    def __init__(self, title: str, *summary: str):
        self.lines = [title.upper(), "=" * display_width(title), *summary]

    def section(self, title: str, *notes: str):
        self.lines += ["", "", title, "-" * display_width(title), *notes]

    def line(self, text: str = ""):
        self.lines.append(text)

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[object]]):
        """Columns of numbers are right-aligned. A row of one string is a divider across the table."""
        if not rows:
            self.lines.append("(none)")
            return
        cells = [[str(cell) for cell in row] for row in rows]
        table_rows = [row for row in cells if len(row) == len(headers)]
        widths = [max((display_width(row[i]) for row in table_rows), default=0) for i in range(len(headers))]
        widths = [max(width, display_width(h)) for width, h in zip(widths, headers)]
        numeric = [all(isinstance(row[i], int) for row in rows if len(row) == len(headers))
                   for i in range(len(headers))]

        def render(row: Sequence[str]) -> str:
            return "  ".join(_pad(cell, w, right) for cell, w, right in zip(row, widths, numeric)).rstrip()

        self.lines += [render(headers), render(["-" * w for w in widths])]
        for row in cells:
            self.lines.append(render(row) if len(row) == len(headers) else f"  {row[0]}")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def write_report(report: Report, name: str, out_dir: Path = OUTPUT_DIR) -> Path:
    """Prints the report and saves it as <out_dir>/<name>.txt. Returns the file's path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.txt"
    path.write_text(report.text(), encoding="utf-8")
    print(report.text(), end="")
    print(f"\n[Saved to {path}]")
    return path
