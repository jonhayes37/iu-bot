"""Tests for commands/end_of_year.py: /end-of-year-results, the top 5 of every category."""

import pytest

from commands.end_of_year import end_of_year_results
from config import Database
from db.hall_of_fame import save_hof_vote
from db.hmas import remove_category, save_hma_vote


@pytest.fixture(autouse=True)
def _databases(databases, frozen_time):
    databases(Database.HMAS, Database.HALL_OF_FAME)
    frozen_time("2026-12-12 12:00:00")


def _vote(category, *ballots, year=2026):
    for user_id, ballot in enumerate(ballots, start=1):
        save_hma_vote(year, user_id, category, *ballot)


def _file(reply):
    attachment = reply.kwargs["file"]
    return attachment.filename, attachment.fp.read().decode("utf-8")


def _section(text, title):
    """The lines of one category's section in the results file."""
    start = text.index(f"### {title} (")
    return text[start:text.index("\n\n", start)].splitlines()


async def _results(admin_interaction, year=None):
    if year is None:
        await end_of_year_results.callback(admin_interaction)
    else:
        await end_of_year_results.callback(admin_interaction, year)
    return admin_interaction.sent[0]


async def test_no_votes_yet(admin_interaction):
    _vote("soty", ("A", "B", "C"), year=2025)

    reply = await _results(admin_interaction)

    assert reply.content == "No votes found for 2026 yet."
    assert "file" not in reply.kwargs


async def test_the_reply_is_private_and_answered_before_counting(admin_interaction):
    save_hof_vote(2026, 1, "IU", "BTS", "EXO")

    await _results(admin_interaction)

    admin_interaction.response.defer.assert_awaited_once_with(ephemeral=True)


async def test_ranks_by_points_and_shows_the_counts(admin_interaction):
    _vote("soty", ("A", "B", "C"), ("A", "C", "B"), ("B", "A", "D"))

    reply = await _results(admin_interaction)

    filename, text = _file(reply)
    assert filename == "2026_end_of_year_results.txt"
    assert reply.content == "✅ Here are the **2026** results."
    assert _section(text, "Song of the Year") == [
        "### Song of the Year (3 ballots) ###",
        "1. A: 8 points (1st: 2, 2nd: 1, 3rd: 0)",
        "2. B: 6 points (1st: 1, 2nd: 1, 3rd: 1)",
        "3. C: 3 points (1st: 0, 2nd: 1, 3rd: 1)",
        "4. D: 1 points (1st: 0, 2nd: 0, 3rd: 1)",
    ]


async def test_equal_points_are_split_by_first_choices(admin_interaction):
    # X and Y both have 4 points; X has a 1st and a 3rd choice, Y two 2nd choices
    _vote("soty", ("X", "Y", "A"), ("B", "Y", "X"))

    _, text = _file(await _results(admin_interaction))

    lines = _section(text, "Song of the Year")
    assert lines[1].startswith("1. X: 4 points") and lines[2].startswith("2. Y: 4 points")
    assert "TIED" not in text


async def test_only_the_top_5_are_listed_with_ties_at_5th_kept(admin_interaction):
    _vote("soty", ("A", "B", "C"), ("D", "E", "F"), ("G", "H", "I"))

    _, text = _file(await _results(admin_interaction))

    # A, D and G tie for 1st; B, E and H tie for 4th, so all six fit in the top 5
    ranks = [line.split(".")[0] for line in _section(text, "Song of the Year")[1:]]
    assert ranks == ["T1", "T1", "T1", "T4", "T4", "T4", "⚠️ TIED FOR 1ST on every count: A, D, G"]


async def test_a_full_tie_for_first_is_flagged_everywhere(admin_interaction):
    _vote("soty", ("A", "B", "C"), ("B", "A", "C"))
    save_hof_vote(2026, 1, "IU", "BTS", "EXO")

    reply = await _results(admin_interaction)

    _, text = _file(reply)
    assert _section(text, "Song of the Year")[1:] == [
        "T1. A: 5 points (1st: 1, 2nd: 1, 3rd: 0)",
        "T1. B: 5 points (1st: 1, 2nd: 1, 3rd: 0)",
        "3. C: 2 points (1st: 0, 2nd: 0, 3rd: 2)",
        "⚠️ TIED FOR 1ST on every count: A, B. Needs a tiebreaker.",
    ]
    assert "⚠️ NEEDS A TIEBREAKER (tied for 1st on every count):\n- Song of the Year: A, B\n" in text
    assert reply.content == "✅ Here are the **2026** results.\n⚠️ Tied for 1st on every count: Song of the Year."


async def test_a_decided_year_says_so(admin_interaction):
    _vote("soty", ("A", "B", "C"))

    _, text = _file(await _results(admin_interaction))

    assert "✅ Every 1st place is decided." in text


async def test_the_hall_of_fame_comes_first_then_each_family(admin_interaction):
    save_hof_vote(2026, 1, "IU", "BTS", "EXO")
    save_hof_vote(2026, 2, "BTS", "IU", "EXO")
    _vote("best_gg", ("IVE", "aespa", "NewJeans"))

    _, text = _file(await _results(admin_interaction))

    assert text.index("████ HALL OF FAME ████") < text.index("████ DAESANG ████") \
        < text.index("████ BONSANG ████") < text.index("████ FUN ████")
    assert _section(text, "HallyU Hall of Fame")[:2] == ["### HallyU Hall of Fame (2 ballots) ###",
                                                       "T1. BTS: 5 points (1st: 1, 2nd: 1, 3rd: 0)"]
    assert _section(text, "Best Girl Group")[0] == "### Best Girl Group (1 ballot) ###"


async def test_a_category_without_votes_says_so(admin_interaction):
    _vote("soty", ("A", "B", "C"))

    _, text = _file(await _results(admin_interaction))

    assert _section(text, "Album of the Year") == ["### Album of the Year (0 ballots) ###", "No votes."]
    assert _section(text, "HallyU Hall of Fame") == ["### HallyU Hall of Fame (0 ballots) ###", "No votes."]


async def test_removed_categories_are_left_out(admin_interaction):
    _vote("soty", ("A", "B", "C"))
    _vote("best_band", ("DAY6", "LUCY", "QWER"))
    remove_category("best_band")

    _, text = _file(await _results(admin_interaction))

    assert "Best Band" not in text


async def test_votes_only_in_a_removed_category_count_as_none(admin_interaction):
    _vote("best_band", ("DAY6", "LUCY", "QWER"))
    remove_category("best_band")

    assert (await _results(admin_interaction)).content == "No votes found for 2026 yet."


async def test_another_year_can_be_counted(admin_interaction, frozen_time):
    _vote("soty", ("Old", "Older", "Oldest"), year=2025)
    frozen_time("2027-02-01 12:00:00")

    filename, text = _file(await _results(admin_interaction, 2025))

    assert filename == "2025_end_of_year_results.txt"
    assert text.startswith("🏆 2025 End of Year Results 🏆")
