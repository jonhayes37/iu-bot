"""Tests for ui/eoy_voting.py: the end of year voting hub and the ranked ballots."""

from unittest import mock

import discord
import pytest

from config import Database
from db.hall_of_fame import get_user_hof_vote, save_hof_vote, set_hof_final_nominees
from db.hmas import get_user_hma_votes, save_hma_vote, set_final_nominees
from ui.base import DATABASE_ERROR
from ui.eoy_voting import (
    EOYVotingHub, HallOfFameVoteButton, HMABallotView, HMACategoryDropdown, HMACategorySelectView, HMAVoteButton,
    HoFVotingView
)
from testsupport.ui import button_labels, choose, match_custom_id

NOMINEES = ["BTS", "IU", "EXO", "Big Bang"]
CATEGORY_LIST_MESSAGE = "**HallyU Music Awards Ballot**\nCategories marked with ⏰ need your vote. ✅ are completed!"


@pytest.fixture(autouse=True)
def _databases(databases, frozen_time):
    databases(Database.HMAS, Database.HALL_OF_FAME)
    frozen_time("2026-10-15 12:00:00")


def _selects(view):
    return view.first_select, view.second_select, view.third_select


class TestHallOfFameVoteButton:
    """Opens the Hall of Fame ballot once nominees are set."""

    async def test_the_button_carries_the_year(self, interaction):
        button = HallOfFameVoteButton(2026)
        rebuilt = await HallOfFameVoteButton.from_custom_id(
            interaction, mock.Mock(), match_custom_id(HallOfFameVoteButton, "btn_vote_hof_2025"))

        assert (button.item.custom_id, button.item.label) == ("btn_vote_hof_2026", "2026 HallyU Hall of Fame")
        assert rebuilt.year == 2025

    @pytest.mark.parametrize("nominees", [[], ["BTS"], ["BTS", "IU"]])
    async def test_fewer_than_three_nominees_means_voting_has_not_started(self, interaction, nominees):
        set_hof_final_nominees(nominees)

        await HallOfFameVoteButton(2026).callback(interaction)

        [reply] = interaction.sent
        assert reply.content == "❌ Voting hasn't started yet! The nominees are still being populated."
        assert reply.ephemeral and "view" not in reply.kwargs

    async def test_opens_a_private_ballot_listing_the_nominees(self, interaction):
        set_hof_final_nominees(NOMINEES)

        await HallOfFameVoteButton(2026).callback(interaction)

        [reply] = interaction.sent
        assert reply.content == "**2026 HallyU Hall of Fame Ballot**\nSelect your top 3 choices below:"
        assert reply.ephemeral
        view = reply.kwargs["view"]
        assert isinstance(view, HoFVotingView)
        assert [o.value for o in view.first_select.options] == sorted(NOMINEES)

    async def test_an_earlier_vote_is_preselected(self, interaction):
        set_hof_final_nominees(NOMINEES)
        save_hof_vote(interaction.user.id, "IU", "BTS", "EXO")

        await HallOfFameVoteButton(2026).callback(interaction)

        view = interaction.sent[0].kwargs["view"]
        assert [(v.def1, v.def2, v.def3) for v in [view]] == [("IU", "BTS", "EXO")]

    async def test_a_database_failure_is_reported(self, interaction, execute):
        execute(Database.HALL_OF_FAME, "DROP TABLE hof_official_nominees")

        await HallOfFameVoteButton(2026).callback(interaction)

        assert interaction.sent[0].content == DATABASE_ERROR


class TestHMAVoteButton:
    """Opens the HMA category picker."""

    async def test_the_button_carries_the_year(self, interaction):
        button = HMAVoteButton(2026)
        rebuilt = await HMAVoteButton.from_custom_id(
            interaction, mock.Mock(), match_custom_id(HMAVoteButton, "btn_vote_hma_2025"))

        assert (button.item.custom_id, button.item.label) == ("btn_vote_hma_2026", "2026 HallyU Music Awards")
        assert rebuilt.year == 2025

    async def test_opens_the_category_list_privately(self, interaction):
        await HMAVoteButton(2026).callback(interaction)

        [reply] = interaction.sent
        assert reply.content == CATEGORY_LIST_MESSAGE
        assert reply.ephemeral
        assert isinstance(reply.kwargs["view"], HMACategorySelectView)


async def test_the_voting_hub_holds_both_buttons_and_never_times_out():
    hub = EOYVotingHub(2026)

    assert hub.timeout is None
    assert button_labels(hub) == ["2026 HallyU Hall of Fame", "2026 HallyU Music Awards"]


class TestHoFVotingView:
    """The three-choice Hall of Fame ballot."""

    async def test_offers_the_nominees_in_all_three_menus_with_no_default_for_a_new_voter(self):
        view = HoFVotingView(2026, NOMINEES)

        for select in _selects(view):
            assert [o.value for o in select.options] == NOMINEES
            assert not any(o.default for o in select.options)
        assert [s.placeholder for s in _selects(view)] == [
            "🥇 1st Choice (3 Points)", "🥈 2nd Choice (2 Points)", "🥉 3rd Choice (1 Point)"]

    async def test_an_earlier_vote_is_the_default_in_each_menu(self):
        view = HoFVotingView(2026, NOMINEES, {"first_choice": "IU", "second_choice": "BTS", "third_choice": "EXO"})

        defaults = [[o.value for o in s.options if o.default] for s in _selects(view)]

        assert defaults == [["IU"], ["BTS"], ["EXO"]]

    async def test_choosing_in_a_menu_only_acknowledges_it(self, interaction):
        view = HoFVotingView(2026, NOMINEES)

        await view.first_select.callback(interaction)

        interaction.response.defer.assert_awaited_once()

    async def test_a_complete_ballot_is_saved_and_shown_back(self, interaction):
        view = HoFVotingView(2026, NOMINEES)
        choose(view.first_select, "IU")
        choose(view.second_select, "BTS")
        choose(view.third_select, "EXO")

        await view.btn_submit.callback(interaction)

        assert get_user_hof_vote(interaction.user.id) == {
            "first_choice": "IU", "second_choice": "BTS", "third_choice": "EXO"}
        [reply] = interaction.sent
        assert reply.via == "edit" and reply.kwargs["view"] is None
        assert reply.embed.title == "🏛️ 2026 Hall of Fame Ballot Secured!"
        assert [(f.name, f.value) for f in reply.embed.fields] == [
            ("🥇 1st Choice", "IU"), ("🥈 2nd Choice", "BTS"), ("🥉 3rd Choice", "EXO")]

    async def test_an_incomplete_ballot_is_refused(self, interaction):
        view = HoFVotingView(2026, NOMINEES)
        choose(view.first_select, "IU")

        await view.btn_submit.callback(interaction)

        [reply] = interaction.sent
        assert reply.content == "❌ **Incomplete Ballot:** You must select a 1st, 2nd, and 3rd choice."
        assert reply.ephemeral
        assert get_user_hof_vote(interaction.user.id) is None

    async def test_voting_for_the_same_nominee_twice_is_refused(self, interaction):
        view = HoFVotingView(2026, NOMINEES)
        choose(view.first_select, "IU")
        choose(view.second_select, "IU")
        choose(view.third_select, "EXO")

        await view.btn_submit.callback(interaction)

        assert interaction.sent[0].content.startswith("❌ **Invalid Ballot:** You cannot vote for the same nominee")
        assert get_user_hof_vote(interaction.user.id) is None

    async def test_unchanged_menus_keep_the_earlier_choices(self, interaction):
        # Only the 2nd choice is changed; the other two menus still show the earlier vote
        view = HoFVotingView(2026, NOMINEES, {"first_choice": "IU", "second_choice": "BTS", "third_choice": "EXO"})
        choose(view.second_select, "Big Bang")

        await view.btn_submit.callback(interaction)

        assert get_user_hof_vote(interaction.user.id) == {
            "first_choice": "IU", "second_choice": "Big Bang", "third_choice": "EXO"}

    async def test_a_change_that_duplicates_an_earlier_choice_is_refused(self, interaction):
        view = HoFVotingView(2026, NOMINEES, {"first_choice": "IU", "second_choice": "BTS", "third_choice": "EXO"})
        choose(view.second_select, "IU")

        await view.btn_submit.callback(interaction)

        assert "Invalid Ballot" in interaction.sent[0].content

    async def test_a_database_failure_is_reported_and_nothing_is_saved(self, interaction, execute):
        execute(Database.HALL_OF_FAME, "DROP TABLE hall_of_fame_votes")
        view = HoFVotingView(2026, NOMINEES)
        for select, name in zip(_selects(view), ("IU", "BTS", "EXO")):
            choose(select, name)

        with pytest.raises(Exception) as caught:
            await view.btn_submit.callback(interaction)
        await view.on_error(interaction, caught.value, view.btn_submit)

        assert interaction.sent[0].content == DATABASE_ERROR

    async def test_the_ballot_times_out_after_15_minutes(self):
        assert HoFVotingView(2026, NOMINEES).timeout == 900


class TestHMABallotView:
    """The ballot for a single HMA category, which returns to the category list."""

    @staticmethod
    def _view(existing=None, user_id=5):
        return HMABallotView(2026, user_id, "soty", "Song of the Year", NOMINEES, existing)

    async def test_offers_the_nominees_and_preselects_an_earlier_vote(self):
        view = self._view({"first_choice": "IU", "second_choice": "BTS", "third_choice": "EXO"})

        assert [o.value for o in view.first_select.options] == NOMINEES
        assert [[o.value for o in s.options if o.default] for s in _selects(view)] == [["IU"], ["BTS"], ["EXO"]]
        assert button_labels(view) == ["Save Vote", "Back to Categories"]

    async def test_saving_stores_the_vote_and_returns_to_the_category_list(self, interaction):
        view = self._view(user_id=interaction.user.id)
        choose(view.first_select, "IU")
        choose(view.second_select, "BTS")
        choose(view.third_select, "EXO")

        await view.btn_save.callback(interaction)

        assert get_user_hma_votes(interaction.user.id)["soty"]["first_choice"] == "IU"
        [reply] = interaction.sent
        assert reply.via == "edit"
        assert reply.content == ("✅ Saved vote for **Song of the Year**!\n\n**HallyU Music Awards Ballot**\n"
                                 "Select your next category:")
        assert isinstance(reply.kwargs["view"], HMACategorySelectView)

    async def test_the_category_list_after_saving_shows_it_as_done(self, interaction):
        view = self._view(user_id=interaction.user.id)
        for select, name in zip(_selects(view), ("IU", "BTS", "EXO")):
            choose(select, name)

        await view.btn_save.callback(interaction)

        options = {o.value: o.emoji.name for d in interaction.sent[0].kwargs["view"].children for o in d.options}
        assert options["soty"] == "✅"
        assert options["aoty"] == "⏰"

    async def test_an_incomplete_vote_is_refused(self, interaction):
        view = self._view()
        choose(view.first_select, "IU")

        await view.btn_save.callback(interaction)

        assert interaction.sent[0].content == "❌ **Incomplete:** Select a 1st, 2nd, and 3rd choice."
        assert get_user_hma_votes(interaction.user.id) == {}

    async def test_a_duplicate_choice_is_refused(self, interaction):
        view = self._view()
        for select, name in zip(_selects(view), ("IU", "IU", "EXO")):
            choose(select, name)

        await view.btn_save.callback(interaction)

        assert interaction.sent[0].content == "❌ **Duplicate:** You cannot vote for the same nominee more than once."
        assert get_user_hma_votes(interaction.user.id) == {}

    async def test_unchanged_menus_keep_the_earlier_choices(self, interaction):
        view = self._view({"first_choice": "IU", "second_choice": "BTS", "third_choice": "EXO"})
        choose(view.third_select, "Big Bang")

        await view.btn_save.callback(interaction)

        vote = get_user_hma_votes(interaction.user.id)["soty"]
        assert (vote["first_choice"], vote["second_choice"], vote["third_choice"]) == ("IU", "BTS", "Big Bang")

    async def test_going_back_saves_nothing(self, interaction):
        view = self._view()
        for select, name in zip(_selects(view), ("IU", "BTS", "EXO")):
            choose(select, name)

        await view.btn_back.callback(interaction)

        [reply] = interaction.sent
        assert reply.via == "edit" and reply.content == CATEGORY_LIST_MESSAGE
        assert isinstance(reply.kwargs["view"], HMACategorySelectView)
        assert get_user_hma_votes(interaction.user.id) == {}

    async def test_choosing_in_a_menu_only_acknowledges_it(self, interaction):
        await self._view().first_select.callback(interaction)

        interaction.response.defer.assert_awaited_once()


class TestHMACategorySelectView:
    """The category picker: unvoted categories first, in menus of at most 25."""

    async def test_every_category_is_offered_unvoted_first_with_their_status(self, interaction):
        save_hma_vote(interaction.user.id, "soty", "A", "B", "C")

        view = HMACategorySelectView(2026, interaction.user.id)

        options = [o for dropdown in view.children for o in dropdown.options]
        marks = [o.emoji.name for o in options]
        assert marks == sorted(marks, key=lambda mark: mark != "⏰")      # every ⏰ before every ✅
        assert marks.count("✅") == 1
        assert next(o for o in options if o.value == "soty").emoji.name == "✅"

    async def test_menus_are_split_into_groups_of_25(self, interaction):
        view = HMACategorySelectView(2026, interaction.user.id)

        sizes = [len(dropdown.options) for dropdown in view.children]

        assert all(isinstance(d, HMACategoryDropdown) for d in view.children)
        assert max(sizes) == 25 and sum(sizes) > 25 and len(sizes) == 2

    async def test_long_category_names_are_shortened_to_fit(self, interaction, execute):
        execute(Database.HMAS, "INSERT INTO hma_categories (category_id, family_id, name) VALUES ('long', 'fun', ?)",
                "x" * 150)

        view = HMACategorySelectView(2026, interaction.user.id)

        long_option = next(o for d in view.children for o in d.options if o.value == "long")
        assert len(long_option.label) == 95

    async def test_votes_from_other_members_do_not_count(self, interaction):
        save_hma_vote(999, "soty", "A", "B", "C")

        view = HMACategorySelectView(2026, interaction.user.id)

        assert "✅" not in [o.emoji.name for d in view.children for o in d.options]


class TestHMACategoryDropdown:
    """Choosing a category opens its ballot, if its final nominees are ready."""

    @staticmethod
    def _dropdown(user_id):
        options = [discord.SelectOption(label="Song of the Year", value="soty"),
                   discord.SelectOption(label="Album of the Year", value="aoty")]
        return HMACategoryDropdown(options, 2026, user_id)

    async def test_a_category_without_enough_nominees_is_not_ready(self, interaction):
        dropdown = self._dropdown(interaction.user.id)
        choose(dropdown, "soty")
        set_final_nominees("soty", ["A", "B"])

        await dropdown.callback(interaction)

        [reply] = interaction.sent
        assert reply.content == "❌ Final nominees for **Song of the Year** are not available yet!"
        assert reply.ephemeral

    async def test_a_ready_category_opens_its_ballot_in_place(self, interaction):
        set_final_nominees("soty", ["A", "B", "C", "D"])
        dropdown = self._dropdown(interaction.user.id)
        choose(dropdown, "soty")

        await dropdown.callback(interaction)

        [reply] = interaction.sent
        assert reply.via == "edit"
        assert reply.content == "**Song of the Year**\nSelect your top 3 choices:"
        ballot = reply.kwargs["view"]
        assert isinstance(ballot, HMABallotView)
        assert (ballot.category_id, ballot.category_name) == ("soty", "Song of the Year")
        assert [o.value for o in ballot.first_select.options] == ["A", "B", "C", "D"]

    async def test_an_earlier_vote_in_the_category_is_preselected(self, interaction):
        set_final_nominees("soty", ["A", "B", "C", "D"])
        save_hma_vote(interaction.user.id, "soty", "B", "C", "D")
        dropdown = self._dropdown(interaction.user.id)
        choose(dropdown, "soty")

        await dropdown.callback(interaction)

        ballot = interaction.sent[0].kwargs["view"]
        assert (ballot.def1, ballot.def2, ballot.def3) == ("B", "C", "D")
