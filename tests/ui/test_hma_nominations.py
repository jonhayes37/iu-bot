"""Tests for ui/hma_nominations.py: nominating one act for several HMA categories at once."""

import pytest

from config import Database
from db.hmas import get_yearly_export_data
from ui.base import DATABASE_ERROR
from ui.hma_nominations import MultiNominationView
from testsupport.ui import button_labels, choose

VIDEO_URL = "https://youtu.be/dQw4w9WgXcQ"


@pytest.fixture(autouse=True)
def _hmas_database(databases, frozen_time):
    databases(Database.HMAS)
    frozen_time("2026-10-15 12:00:00")


async def _press_submit(interaction, view):
    await view.submit_btn.callback(interaction)


class TestBallotSetup:
    """The three dropdowns list the active categories of each family."""

    async def test_has_a_dropdown_per_family_and_a_submit_button(self):
        view = MultiNominationView("IVE - HEYA")

        assert [s.placeholder for s in (view.daesang_select, view.bonsang_select, view.fun_select)] == \
            ["Select Daesangs...", "Select Bonsangs...", "Select Fun Awards..."]
        assert button_labels(view) == ["Submit Nominations"]

    async def test_the_daesang_dropdown_lists_the_daesangs_by_name(self):
        view = MultiNominationView("IVE - HEYA")

        assert {(o.value, o.label) for o in view.daesang_select.options} >= {
            ("soty", "Song of the Year"), ("aoty", "Album of the Year")}

    async def test_any_number_of_categories_can_be_ticked_including_none(self):
        view = MultiNominationView("IVE - HEYA")

        for select in (view.daesang_select, view.bonsang_select, view.fun_select):
            assert select.min_values == 0
            assert select.max_values == len(select.options)

    async def test_a_retired_category_is_not_offered(self, execute):
        execute(Database.HMAS, "UPDATE hma_categories SET is_active = 0 WHERE category_id = 'soty'")

        view = MultiNominationView("IVE - HEYA")

        assert "soty" not in [o.value for o in view.daesang_select.options]

    async def test_no_dropdown_exceeds_discords_limit_of_25_options(self):
        view = MultiNominationView("x")

        assert all(0 < len(s.options) <= 25 for s in (view.daesang_select, view.bonsang_select, view.fun_select))

    async def test_picking_in_a_dropdown_only_acknowledges_it(self, interaction):
        view = MultiNominationView("IVE - HEYA")

        await view.daesang_select.callback(interaction)

        interaction.response.defer.assert_awaited_once()
        assert interaction.sent == []

    async def test_the_view_times_out_after_15_minutes(self):
        assert MultiNominationView("x").timeout == 900


class TestSubmitNominations:
    """Pressing Submit saves one nomination per ticked category."""

    async def test_nominations_are_saved_for_every_ticked_category_across_dropdowns(self, interaction):
        view = MultiNominationView("IVE - HEYA")
        choose(view.daesang_select, "soty")
        choose(view.bonsang_select, "best_gg", "best_collab")

        await _press_submit(interaction, view)

        export = get_yearly_export_data(2026)
        assert export["Daesang"]["Song of the Year"] == [(interaction.user.id, "IVE - HEYA")]
        assert export["Bonsang"]["Best Girl Group"] == [(interaction.user.id, "IVE - HEYA")]
        assert export["Bonsang"]["Best Collaboration"] == [(interaction.user.id, "IVE - HEYA")]
        assert sum(len(c) for c in export.values()) == 3

    async def test_the_confirmation_replaces_the_dropdowns_and_lists_the_categories(self, interaction):
        view = MultiNominationView("IVE - HEYA")
        choose(view.daesang_select, "soty")
        choose(view.bonsang_select, "best_gg")

        await _press_submit(interaction, view)

        [reply] = interaction.sent
        assert reply.via == "edit"
        assert reply.kwargs["view"] is None and reply.content is None
        assert reply.embed.title == "🏆 Nominations Submitted!"
        assert "**2026 HallyU Music Awards**" in reply.embed.description
        fields = {f.name: f.value for f in reply.embed.fields}
        assert fields["Nominee"] == "**IVE - HEYA**"
        assert fields["Categories"] == "• Song of the Year\n• Best Girl Group"

    async def test_a_december_nomination_is_for_next_years_awards(self, interaction, frozen_time):
        frozen_time("2026-12-03 12:00:00")
        view = MultiNominationView("IVE - HEYA")
        choose(view.daesang_select, "soty")

        await _press_submit(interaction, view)

        assert "**2027 HallyU Music Awards**" in interaction.sent[0].embed.description

    async def test_ticking_nothing_is_refused_privately(self, interaction):
        view = MultiNominationView("IVE - HEYA")

        await _press_submit(interaction, view)

        [reply] = interaction.sent
        assert (reply.content, reply.ephemeral) == ("❌ You must select at least one category!", True)
        assert not get_yearly_export_data(2026)

    @pytest.mark.parametrize("category", ["best_dance_cover", "best_vocal_cover"])
    async def test_cover_categories_need_a_youtube_link_in_the_nominee(self, interaction, category):
        view = MultiNominationView("Some dance cover")
        choose(view.bonsang_select, category)

        await _press_submit(interaction, view)

        assert interaction.sent[0].content.startswith(
            "❌ Nominations for Best Dance/Vocal Cover must include a valid YouTube URL")
        assert not get_yearly_export_data(2026)

    @pytest.mark.parametrize("category", ["best_dance_cover", "best_vocal_cover"])
    async def test_a_cover_with_a_link_is_accepted(self, interaction, category):
        view = MultiNominationView(f"My cover {VIDEO_URL}")
        choose(view.bonsang_select, category)

        await _press_submit(interaction, view)

        assert interaction.sent[0].embed.title == "🏆 Nominations Submitted!"

    async def test_other_categories_do_not_need_a_link(self, interaction):
        view = MultiNominationView("IVE - HEYA")
        choose(view.bonsang_select, "best_gg")

        await _press_submit(interaction, view)

        assert interaction.sent[0].embed is not None

    async def test_one_cover_category_among_others_still_needs_the_link(self, interaction):
        view = MultiNominationView("IVE - HEYA")
        choose(view.daesang_select, "soty")
        choose(view.bonsang_select, "best_dance_cover")

        await _press_submit(interaction, view)

        assert "YouTube URL" in interaction.sent[0].content
        assert not get_yearly_export_data(2026)

    async def test_a_database_failure_is_reported_and_nothing_is_saved(self, interaction, execute):
        execute(Database.HMAS, "DROP TABLE hma_nominations")
        view = MultiNominationView("IVE - HEYA")
        choose(view.daesang_select, "soty")

        with pytest.raises(Exception) as caught:
            await _press_submit(interaction, view)
        await view.on_error(interaction, caught.value, view.submit_btn)

        assert interaction.sent[0].content == DATABASE_ERROR
