"""Tests for ui/eoy_nominations.py: the end of year nominations hub, its buttons and forms."""

import sqlite3
from unittest import mock

import pytest

from config import Database
from db.hall_of_fame import get_hof_nomination, save_hof_nomination
from db.top_songs import get_all_top_songs, get_user_top_songs, save_top_songs
from ui.base import DATABASE_ERROR
from ui.eoy_nominations import (
    EOYNominationsHub, HallOfFameNominationButton, HoFModal, Top25Button, Top25Modal
)
from testsupport.ui import button_labels, fill, match_custom_id, text_input_label

TWENTY_FIVE = "\n".join(f"Artist {i} - Song {i}" for i in range(1, 26))
THREE = "IU - Blueming\nIVE - All Night\nBTS - Butter"


@pytest.fixture(autouse=True)
def _databases(databases, frozen_time):
    databases(Database.TOP_SONGS, Database.HALL_OF_FAME)
    frozen_time("2026-10-15 12:00:00")


async def _submit_top25(interaction, t25=TWENTY_FIVE, hms=THREE, year=2026):
    modal = Top25Modal(year)
    fill(modal.top_25, t25)
    fill(modal.hms, hms)
    await modal.on_submit(interaction)
    return modal


class TestTop25Modal:
    """The Top 25 Songs and honourable mentions form."""

    async def test_the_form_is_titled_and_labelled_for_the_year(self):
        modal = Top25Modal(2026)

        assert modal.title == "2026 End of Year: Top 25 Songs"
        assert text_input_label(modal.top_25) == "Your 2026 Top 25 Songs"
        assert (modal.top_25.max_length, modal.hms.max_length) == (4000, 1000)

    async def test_an_earlier_submission_fills_the_boxes(self):
        modal = Top25Modal(2026, existing_t25="old list", existing_hms="old mentions")

        assert (modal.top_25.default, modal.hms.default) == ("old list", "old mentions")

    async def test_valid_lists_are_saved_cleaned_and_confirmed(self, interaction):
        await _submit_top25(interaction)

        saved = get_all_top_songs()[0]
        assert (saved["user_id"], saved["username"], saved["award_year"]) == \
            (interaction.user.id, interaction.user.display_name, 2026)
        assert saved["top_25_raw"] == TWENTY_FIVE
        assert saved["top_25_clean"].splitlines()[0] == "1. Artist 1 // Song 1"
        assert saved["hms_clean"] == "1. IU // Blueming\n2. IVE // All Night\n3. BTS // Butter"
        [reply] = interaction.sent
        assert reply.ephemeral
        assert reply.embed.title == "🎵 2026 Top 25 Submitted!"
        assert "Top 25 Songs of 2026" in reply.embed.description

    async def test_links_are_kept_for_the_playlist(self, interaction):
        lines = TWENTY_FIVE.splitlines()
        lines[0] += " (https://youtu.be/aaaaaaaaaaa)"

        await _submit_top25(interaction, "\n".join(lines))

        assert get_all_top_songs()[0]["top_25_urls"].startswith("https://youtu.be/aaaaaaaaaaa,")

    async def test_a_top_25_of_the_wrong_length_is_refused_and_both_lists_handed_back(self, interaction):
        short = "\n".join(TWENTY_FIVE.splitlines()[:24])

        await _submit_top25(interaction, short)

        [reply] = interaction.sent
        assert "**Top 25:** Your main list requires exactly 25 songs, but you provided 24." in reply.content
        assert "Honourable Mentions" not in reply.content
        assert [(f.filename, f.fp.read()) for f in reply.kwargs["files"]] == [
            ("top_25.txt", short.encode()), ("honourable_mentions.txt", THREE.encode())]
        assert get_all_top_songs() == []

    async def test_both_problems_are_listed_together(self, interaction):
        await _submit_top25(interaction, "just one", "IU - a\nIVE - b")

        content = interaction.sent[0].content
        assert "**Top 25:**" in content and "**Honourable Mentions:**" in content
        assert "exactly 3 songs, but you provided 2" in content

    async def test_an_empty_honourable_mentions_box_is_not_attached(self, interaction):
        await _submit_top25(interaction, "just one", "")

        assert [f.filename for f in interaction.sent[0].kwargs["files"]] == ["top_25.txt"]

    async def test_resubmitting_replaces_the_earlier_list(self, interaction):
        await _submit_top25(interaction)
        interaction.sent.clear()

        await _submit_top25(interaction, TWENTY_FIVE.replace("Song 1\n", "Different\n", 1))

        assert len(get_all_top_songs()) == 1

    async def test_a_failed_save_hands_both_lists_back(self, interaction, execute):
        execute(Database.TOP_SONGS, "DROP TABLE eoy_top_songs")
        modal = Top25Modal(2026)
        fill(modal.top_25, TWENTY_FIVE)
        fill(modal.hms, THREE)

        with pytest.raises(Exception) as caught:
            await modal.on_submit(interaction)
        await modal.on_error(interaction, caught.value)

        [reply] = interaction.sent
        assert reply.content.startswith(DATABASE_ERROR)
        assert [f.filename for f in reply.kwargs["files"]] == ["top_25.txt", "honourable_mentions.txt"]


class TestHoFModal:
    """The Hall of Fame nomination form."""

    async def test_the_form_is_set_up_for_the_year(self):
        modal = HoFModal(2026, existing_text="BTS")

        assert modal.title == "2026 Hall of Fame Nominations"
        assert text_input_label(modal.hof_text) == "Who should be inducted in 2026?"
        assert modal.hof_text.default == "BTS"

    async def test_submitting_saves_and_confirms_the_award_year(self, interaction):
        modal = HoFModal(2026)
        fill(modal.hof_text, "BTS, Girls' Generation")

        await modal.on_submit(interaction)

        assert get_hof_nomination(interaction.user.id) == "BTS, Girls' Generation"
        [reply] = interaction.sent
        assert reply.ephemeral
        assert reply.embed.title == "🏛️ HallyU Hall of Fame Nominations Submitted!"
        assert "**2026 HallyU Hall of Fame**" in reply.embed.description

    async def test_a_december_nomination_is_confirmed_for_next_year(self, interaction, frozen_time):
        frozen_time("2026-12-05 12:00:00")
        modal = HoFModal(2027)
        fill(modal.hof_text, "IU")

        await modal.on_submit(interaction)

        assert "**2027 HallyU Hall of Fame**" in interaction.sent[0].embed.description

    async def test_a_failed_save_hands_the_text_back(self, interaction, execute):
        execute(Database.HALL_OF_FAME, "DROP TABLE hall_of_fame_nominations")
        modal = HoFModal(2026)
        fill(modal.hof_text, "BTS")

        await modal.on_error(interaction, sqlite3.Error("x"))

        [reply] = interaction.sent
        assert reply.content.startswith(DATABASE_ERROR)
        assert [(f.filename, f.fp.read()) for f in reply.kwargs["files"]] == [("hall_of_fame.txt", b"BTS")]


class TestButtons:
    """The hub's buttons carry the year, so hubs from any year work after a restart."""

    async def test_the_top_25_button(self):
        button = Top25Button(2026)

        assert (button.item.custom_id, button.item.label) == ("btn_top25_2026", "Submit 2026 Top 25 Songs")

    async def test_the_hall_of_fame_button(self):
        button = HallOfFameNominationButton(2026)

        assert (button.item.custom_id, button.item.label) == ("btn_nom_hof_2026", "2026 HallyU Hall of Fame")

    @pytest.mark.parametrize("button_class, custom_id", [
        (Top25Button, "btn_top25_2025"), (HallOfFameNominationButton, "btn_nom_hof_2025")])
    async def test_a_button_is_rebuilt_with_its_year_after_a_restart(self, interaction, button_class, custom_id):
        match = match_custom_id(button_class, custom_id)

        rebuilt = await button_class.from_custom_id(interaction, mock.Mock(), match)

        assert rebuilt.year == 2025

    async def test_the_ids_are_not_confused_with_each_other(self):
        assert match_custom_id(Top25Button, "btn_nom_hof_2026") is None
        assert match_custom_id(HallOfFameNominationButton, "btn_top25_2026") is None
        assert match_custom_id(Top25Button, "btn_top25_year") is None

    async def test_the_top_25_button_opens_an_empty_form_for_a_new_submitter(self, interaction):
        await Top25Button(2026).callback(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, Top25Modal)
        assert (modal.year, modal.top_25.default, modal.hms.default) == (2026, None, None)

    async def test_the_top_25_button_prefills_an_earlier_submission(self, interaction):
        save_top_songs(interaction.user.id, "jo", "raw25", "c", "", "rawhm", "c", "")

        await Top25Button(2026).callback(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        assert (modal.top_25.default, modal.hms.default) == ("raw25", "rawhm")
        assert get_user_top_songs(interaction.user.id)

    async def test_the_hall_of_fame_button_prefills_an_earlier_nomination(self, interaction):
        save_hof_nomination(interaction.user.id, "jo", "BTS")

        await HallOfFameNominationButton(2026).callback(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, HoFModal)
        assert (modal.year, modal.hof_text.default) == (2026, "BTS")

    async def test_a_database_failure_is_reported_to_the_user(self, interaction, execute):
        execute(Database.TOP_SONGS, "DROP TABLE eoy_top_songs")

        await Top25Button(2026).callback(interaction)

        assert interaction.sent[0].content == DATABASE_ERROR


async def test_the_hub_holds_both_buttons_and_never_times_out():
    hub = EOYNominationsHub(2026)

    assert hub.timeout is None
    assert button_labels(hub) == ["Submit 2026 Top 25 Songs", "2026 HallyU Hall of Fame"]
