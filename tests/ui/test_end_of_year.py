"""Tests for ui/end_of_year.py and the end of year buttons, forms and ballots once the year is closed."""

import pytest

from config import Database
from db.bot import close_end_of_year
from db.hall_of_fame import get_all_hof_nominations, get_hof_ballots, set_hof_final_nominees
from db.hmas import (
    get_active_hma_categories, get_all_category_suggestions, get_hma_ballots, get_yearly_export_data,
    set_final_nominees
)
from db.top_songs import get_all_top_songs
from ui.end_of_year import closed_message, refuse_if_closed
from ui.eoy_nominations import EOYNominationsHub, HallOfFameNominationButton, HoFModal, Top25Button, Top25Modal
from ui.eoy_voting import EOYVotingHub, HallOfFameVoteButton, HMABallotView, HMAVoteButton, HoFVotingView
from ui.hma_nominations import HMANominationsButton, NominationPageButton, NominationPageModal, nomination_pages
from ui.hma_suggestions import HMACategorySuggestionModal, HMASuggestButton, HMASuggestionsHub
from testsupport.ui import choose, fill

NOMINEES = ["BTS", "IU", "EXO"]
TWENTY_FIVE = "\n".join(f"Artist {i} - Song {i}" for i in range(1, 26))


@pytest.fixture(autouse=True)
def _databases(databases, frozen_time):
    databases(Database.BOT, Database.HMAS, Database.HALL_OF_FAME, Database.TOP_SONGS)
    frozen_time("2026-12-12 12:00:00")
    set_hof_final_nominees(2026, NOMINEES)
    set_final_nominees(2026, "soty", NOMINEES)


def _ranked(view):
    for select, name in zip((view.first_select, view.second_select, view.third_select), NOMINEES):
        choose(select, name)
    return view


async def _top_25_form(interaction):
    modal = Top25Modal(2026)
    fill(modal.top_25, TWENTY_FIVE)
    fill(modal.hms, "IU - a\nIVE - b\nBTS - c")
    await modal.on_submit(interaction)


async def _hof_form(interaction):
    modal = HoFModal(2026)
    fill(modal.hof_text, "BTS")
    await modal.on_submit(interaction)


async def _suggestion_form(interaction):
    modal = HMACategorySuggestionModal(2026)
    fill(modal.new_cats, "Best Fancam")
    fill(modal.drop_cats, "")
    await modal.on_submit(interaction)


async def _hof_ballot(interaction):
    await _ranked(HoFVotingView(2026, NOMINEES)).btn_submit.callback(interaction)


async def _hma_ballot(interaction):
    view = _ranked(HMABallotView(2026, interaction.user.id, "soty", "Song of the Year", NOMINEES))
    await view.btn_save.callback(interaction)


async def _hma_nomination_form(interaction):
    pages = nomination_pages(get_active_hma_categories())
    modal = NominationPageModal(2026, pages[0], len(pages), {})
    fill(modal.boxes["soty"], "IVE - HEYA")
    await modal.on_submit(interaction)


EVERY_WAY_IN = {
    "top 25 button": lambda i: Top25Button(2026).callback(i),
    "top 25 form": _top_25_form,
    "hall of fame nomination button": lambda i: HallOfFameNominationButton(2026).callback(i),
    "hall of fame nomination form": _hof_form,
    "suggestions button": lambda i: HMASuggestButton(2026).callback(i),
    "suggestions form": _suggestion_form,
    "hall of fame vote button": lambda i: HallOfFameVoteButton(2026).callback(i),
    "hall of fame ballot": _hof_ballot,
    "hma vote button": lambda i: HMAVoteButton(2026).callback(i),
    "hma ballot": _hma_ballot,
    "hma nominations button": lambda i: HMANominationsButton(2026).callback(i),
    "hma nomination page button": lambda i: NominationPageButton(2026, 1).callback(i),
    "hma nomination form": _hma_nomination_form,
}


@pytest.mark.parametrize("use", EVERY_WAY_IN.values(), ids=EVERY_WAY_IN.keys())
async def test_once_the_year_is_closed_everything_refuses_and_saves_nothing(interaction, use):
    close_end_of_year(2026)

    await use(interaction)

    [reply] = interaction.sent
    assert (reply.content, reply.ephemeral) == (closed_message(2026), True)
    interaction.response.send_modal.assert_not_awaited()
    assert get_all_top_songs(2026) == [] and get_all_hof_nominations(2026) == []
    assert get_all_category_suggestions(2026) == [] and not get_yearly_export_data(2026)
    assert get_hof_ballots(2026) == [] and not get_hma_ballots(2026)


@pytest.mark.parametrize("use", EVERY_WAY_IN.values(), ids=EVERY_WAY_IN.keys())
async def test_closing_another_year_changes_nothing(interaction, use):
    close_end_of_year(2025)

    await use(interaction)

    assert all(sent.content != closed_message(2025) for sent in interaction.sent)


async def test_refuse_if_closed_lets_an_open_year_through(interaction):
    assert await refuse_if_closed(interaction, 2026) is False
    assert interaction.sent == []


def test_the_closed_message_names_the_year():
    assert closed_message(2026).startswith("🔒 The 2026 end of year festivities are closed")


@pytest.mark.parametrize("hub", [HMASuggestionsHub, EOYNominationsHub, EOYVotingHub])
async def test_a_closed_hub_greys_out_its_buttons_and_an_open_one_does_not(hub):
    assert all(button.item.disabled for button in hub(2026, closed=True).children)
    assert not any(button.item.disabled for button in hub(2026).children)
