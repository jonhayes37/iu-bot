"""
Text the charts can draw. matplotlib can't draw colour emoji, so a name like "Alexrandia 🖤🩶🤍💜" is
shown as "Alexrandia" rather than with empty boxes. Korean, Japanese and Chinese are drawn with a
fallback font when one is installed (macOS and Windows have one; add one elsewhere if titles need it).
"""

from functools import cache

from matplotlib import font_manager, rcParams

MAIN_FAMILY = "DejaVu Sans"  # matplotlib's own font, always there
# The first of these that's installed is used where the main font has no glyph (only one, since matplotlib
# looks up every listed font in bold for bold text and complains about each that has none)
FALLBACK_FAMILIES = ("Apple SD Gothic Neo", "AppleGothic", "Malgun Gothic", "Noto Sans CJK KR", "Noto Sans KR",
                     "NanumGothic", "Hiragino Sans")


@cache
def chart_families() -> tuple[str, ...]:
    installed = {font.name for font in font_manager.fontManager.ttflist}
    return (MAIN_FAMILY, *[family for family in FALLBACK_FAMILIES if family in installed][:1])


@cache
def _drawable_codepoints() -> frozenset[int]:
    codepoints: set[int] = set()
    for family in chart_families():
        path = font_manager.findfont(font_manager.FontProperties(family=family), fallback_to_default=False)
        codepoints |= set(font_manager.get_font(path).get_charmap())
    return frozenset(codepoints)


def use_chart_fonts():
    """Makes the text drawn from here on use the main font, then the fallbacks for what it lacks."""
    rcParams["font.family"] = list(chart_families())


def drawable(text: str) -> str:
    """
    The text without the characters no chart font has (emoji), with its spacing tidied. The text as it
    was if nothing would be left.
    """
    codepoints = _drawable_codepoints()
    kept = " ".join("".join(char for char in text if ord(char) in codepoints or char.isspace()).split())
    return kept or text
