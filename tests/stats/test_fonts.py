"""Text the charts can draw."""

from matplotlib import rcParams

from stats.common.fonts import MAIN_FAMILY, chart_families, drawable, use_chart_fonts


def test_emoji_are_left_out():
    assert drawable("Alexrandia 🖤🩶🤍💜") == "Alexrandia"
    assert drawable("Kat 🌸 Kpop") == "Kat Kpop"


def test_letters_the_main_font_has_are_kept():
    assert drawable("ɱαɳɳყႦ") == "ɱαɳɳყႦ"
    assert drawable("IVE // Rebel Heart") == "IVE // Rebel Heart"


def test_a_name_of_only_emoji_is_kept_as_it_was():
    assert drawable("🖤🩶") == "🖤🩶"


def test_the_charts_use_the_main_font_first():
    use_chart_fonts()

    assert chart_families()[0] == MAIN_FAMILY
    assert list(rcParams["font.family"]) == list(chart_families())
