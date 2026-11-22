"""Tests for commands/hall_of_fame.py"""

from typing import Callable, NamedTuple

import pytest
from discord import app_commands

from commands.hall_of_fame import add_hall_of_famer, add_lifetime_achiever, hall_of_fame_set_nominees
from config import Database
from db.hall_of_fame import Inductee, get_hall_of_famers, get_lifetime_achievers, get_official_hof_nominees
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


class InductionCommand(NamedTuple):
    """One of the two commands, where it records and what it says."""
    command: app_commands.Command
    recorded: Callable[[], list[Inductee]]
    confirmation: str  # for IU in 2026
    where: str  # how a repeat is described


INDUCTION_COMMANDS = [
    pytest.param(InductionCommand(add_hall_of_famer, get_hall_of_famers,
                                  "🏛️ **IU** is in the Hall of Fame (class of 2026).", "in the Hall of Fame"),
                 id="hall of fame"),
    pytest.param(InductionCommand(add_lifetime_achiever, get_lifetime_achievers,
                                  "🌟 **IU** has the lifetime achievement award (2026).",
                                  "a lifetime achievement award winner"),
                 id="lifetime achievement"),
]


@pytest.mark.usefixtures("no_inductees")
@pytest.mark.parametrize("induction", INDUCTION_COMMANDS)
class TestInductionCommands:
    """/add-hall-of-famer and /add-lifetime-achiever record a name for the current calendar year."""

    async def test_the_name_is_recorded_for_this_year(self, admin_interaction, induction):
        await induction.command.callback(admin_interaction, "  IU ")

        assert induction.recorded() == [Inductee("IU", 2026)]
        [reply] = admin_interaction.sent
        assert (reply.content, reply.ephemeral) == (induction.confirmation, True)

    async def test_run_in_december_it_is_still_this_years_class(self, admin_interaction, frozen_time, induction):
        frozen_time("2027-01-01 03:00:00")  # still December 31 in Toronto

        await induction.command.callback(admin_interaction, "IU")

        assert induction.recorded() == [Inductee("IU", 2026)]

    async def test_a_name_already_in_is_left_alone(self, admin_interaction, frozen_time, induction):
        frozen_time("2024-12-10 12:00:00")
        await induction.command.callback(admin_interaction, "Girls' Generation")
        frozen_time("2026-12-10 12:00:00")

        await induction.command.callback(admin_interaction, "girls' generation")

        assert induction.recorded() == [Inductee("Girls' Generation", 2024)]
        [_, reply] = admin_interaction.sent
        assert reply.content == (f"ℹ️ **Girls' Generation** is already {induction.where} (since 2024), "
                                 "so nothing changed.")
        assert reply.ephemeral

    async def test_a_blank_name_is_refused(self, admin_interaction, induction):
        await induction.command.callback(admin_interaction, "   ")

        assert admin_interaction.sent[0].content == "❌ The name can't be blank."
        assert induction.recorded() == []


async def test_a_seeded_hall_of_famer_is_already_in(admin_interaction):
    await add_hall_of_famer.callback(admin_interaction, "girls' generation")

    assert admin_interaction.sent[0].content == (
        "ℹ️ **Girls' Generation** is already in the Hall of Fame (since 2020), so nothing changed.")
