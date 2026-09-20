"""Tests for commands/hall_of_fame.py"""

import pytest

from commands.hall_of_fame import hall_of_fame_set_nominees
from config import Database
from db.hall_of_fame import get_official_hof_nominees


@pytest.fixture(autouse=True)
def _hall_of_fame_database(databases, frozen_time):
    databases(Database.HALL_OF_FAME)
    frozen_time("2026-10-15 12:00:00")


async def test_sets_the_shortlist_and_confirms_each_name(admin_interaction):
    await hall_of_fame_set_nominees.callback(admin_interaction, "BTS | Girls' Generation |  Seventeen ")

    assert get_official_hof_nominees() == ["BTS", "Girls' Generation", "Seventeen"]
    [reply] = admin_interaction.sent
    assert reply.content == ("✅ **Saved 3 Hall of Fame nominees for 2026!**\n\n"
                             "• BTS\n• Girls' Generation\n• Seventeen")


@pytest.mark.parametrize("text", ["", "   ", "|", " | | "])
async def test_a_list_with_no_names_is_refused(admin_interaction, text):
    await hall_of_fame_set_nominees.callback(admin_interaction, text)

    assert admin_interaction.sent[0].content == "❌ No valid nominees found. Check your formatting."
    assert get_official_hof_nominees() == []


async def test_setting_again_replaces_the_list(admin_interaction):
    await hall_of_fame_set_nominees.callback(admin_interaction, "BTS | IU")

    await hall_of_fame_set_nominees.callback(admin_interaction, "EXO")

    assert get_official_hof_nominees() == ["EXO"]


async def test_the_reply_is_private_and_uses_the_awards_year(admin_interaction, frozen_time):
    frozen_time("2026-12-05 12:00:00")

    await hall_of_fame_set_nominees.callback(admin_interaction, "BTS")

    admin_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert "for 2027!" in admin_interaction.sent[0].content
