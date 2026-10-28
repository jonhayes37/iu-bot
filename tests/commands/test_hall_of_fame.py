"""Tests for commands/hall_of_fame.py"""

import pytest

from commands.hall_of_fame import hall_of_fame_set_nominees
from config import Database
from db.hall_of_fame import get_official_hof_nominees
from utils.validation import MAX_BALLOT_NOMINEES, MAX_BALLOT_NOMINEE_LENGTH


@pytest.fixture(autouse=True)
def _hall_of_fame_database(databases, frozen_time):
    databases(Database.HALL_OF_FAME)
    frozen_time("2026-10-15 12:00:00")


async def test_sets_the_shortlist_and_confirms_each_name(admin_interaction):
    await hall_of_fame_set_nominees.callback(admin_interaction, "BTS | Girls' Generation |  Seventeen ")

    assert get_official_hof_nominees(2026) == ["BTS", "Girls' Generation", "Seventeen"]
    [reply] = admin_interaction.sent
    assert reply.content == ("✅ **Saved 3 Hall of Fame nominees for 2026!**\n\n"
                             "• BTS\n• Girls' Generation\n• Seventeen")


@pytest.mark.parametrize("text", ["", "   ", "|", " | | "])
async def test_a_list_with_no_names_is_refused(admin_interaction, text):
    await hall_of_fame_set_nominees.callback(admin_interaction, text)

    assert admin_interaction.sent[0].content == "❌ No valid nominees found. Check your formatting."
    assert get_official_hof_nominees(2026) == []


async def test_setting_again_replaces_the_list(admin_interaction):
    await hall_of_fame_set_nominees.callback(admin_interaction, "BTS | IU | BIGBANG")

    await hall_of_fame_set_nominees.callback(admin_interaction, "EXO | SHINee | 2NE1")

    assert get_official_hof_nominees(2026) == ["2NE1", "EXO", "SHINee"]


async def test_in_december_the_shortlist_is_for_the_year_being_celebrated(admin_interaction, frozen_time):
    frozen_time("2026-12-05 12:00:00")

    await hall_of_fame_set_nominees.callback(admin_interaction, "BTS | IU | EXO")

    admin_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert "for 2026!" in admin_interaction.sent[0].content
    assert get_official_hof_nominees(2026) == ["BTS", "EXO", "IU"]


@pytest.mark.parametrize("text, message_start", [
    ("BTS | IU", "❌ You gave 2 nominees, but voters rank their top 3"),
    (" | ".join(f"Act {i}" for i in range(MAX_BALLOT_NOMINEES + 1)), "❌ You gave 26 nominees, but a voting menu"),
    ("BTS | IU | BTS", "❌ The list has the same nominee more than once."),
    (f"BTS | IU | {'x' * (MAX_BALLOT_NOMINEE_LENGTH + 1)}", "❌ A voting menu shows at most 100 characters"),
])
async def test_a_list_the_ballot_cannot_show_is_refused_and_nothing_changes(admin_interaction, text, message_start):
    await hall_of_fame_set_nominees.callback(admin_interaction, "BTS | IU | EXO")

    await hall_of_fame_set_nominees.callback(admin_interaction, text)

    assert admin_interaction.sent[-1].content.startswith(message_start)
    assert get_official_hof_nominees(2026) == ["BTS", "EXO", "IU"]
