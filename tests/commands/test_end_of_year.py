"""Tests for commands/end_of_year.py: the nominations hub, the export and the voting hub."""

import pytest

from commands.end_of_year import end_of_year_nominations, end_of_year_voting, export_eoy_nominations
from config import Database
from db.hall_of_fame import save_hof_nomination
from db.top_songs import save_top_songs
from ui.eoy_nominations import EOYNominationsHub
from ui.eoy_voting import EOYVotingHub
from testsupport.ui import button_labels


@pytest.fixture(autouse=True)
def _databases(databases, frozen_time):
    databases(Database.TOP_SONGS, Database.HALL_OF_FAME)
    frozen_time("2026-10-15 12:00:00")


def _files(reply):
    return {f.filename: f.fp.read().decode("utf-8") for f in reply.kwargs["files"]}


class TestNominationsHub:
    """/end-of-year-nominations posts the hub in the channel."""

    async def test_posts_the_hub_for_the_current_awards_year(self, admin_interaction):
        await end_of_year_nominations.callback(admin_interaction)

        [hub] = admin_interaction.channel.sent
        assert hub.embed.title == "2026 End of Year Nominations!"
        assert "**2. HallyU Hall of Fame:** Nominate the K-Pop legends who deserve to be in our 2026 class of " \
            "inductees!" in hub.embed.description
        assert isinstance(hub.kwargs["view"], EOYNominationsHub)
        assert button_labels(hub.kwargs["view"]) == ["Submit 2026 Top 25 Songs", "2026 HallyU Hall of Fame"]

    async def test_in_december_it_is_for_next_year(self, admin_interaction, frozen_time):
        frozen_time("2026-12-02 12:00:00")

        await end_of_year_nominations.callback(admin_interaction)

        assert admin_interaction.channel.sent[0].embed.title == "2027 End of Year Nominations!"

    async def test_the_admin_is_told_privately_that_it_worked(self, admin_interaction):
        await end_of_year_nominations.callback(admin_interaction)

        admin_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        [reply] = admin_interaction.sent
        assert (reply.via, reply.content) == ("followup", "End of Year Hub posted successfully!")


class TestExport:
    """/export-end-of-year-nominations attaches everything submitted this year."""

    async def test_nothing_submitted_yet(self, admin_interaction):
        await export_eoy_nominations.callback(admin_interaction)

        [reply] = admin_interaction.sent
        assert reply.content == "No End of Year submissions found for 2026 yet!"
        assert "files" not in reply.kwargs

    async def test_attaches_a_file_each_for_top_25s_mentions_and_the_hall_of_fame(self, admin_interaction):
        save_top_songs(1, "Jo", "raw", "1. A // a\n2. B // b", "", "raw", "1. X // x", "")
        save_top_songs(2, "Sam", "raw", "1. C // c", "", "", "", "")
        save_hof_nomination(1, "Jo", "BTS, Girls' Generation")

        await export_eoy_nominations.callback(admin_interaction)

        [reply] = admin_interaction.sent
        assert reply.content == "✅ Exported **2** Top 25 lists and **1** Hall of Fame ballots for **2026**!"
        files = _files(reply)
        assert files["top_25_2026.txt"] == "--- Jo ---\n1. A // a\n2. B // b\n\n--- Sam ---\n1. C // c\n\n"
        assert files["honourable_mentions_2026.txt"] == "--- Jo ---\n1. X // x\n\n"     # Sam left his blank
        assert files["hall_of_fame_2026.txt"] == "--- Jo ---\nBTS, Girls' Generation\n\n"

    async def test_a_file_is_only_attached_when_it_has_content(self, admin_interaction):
        save_hof_nomination(1, "Jo", "BTS")

        await export_eoy_nominations.callback(admin_interaction)

        assert list(_files(admin_interaction.sent[0])) == ["hall_of_fame_2026.txt"]
        assert admin_interaction.sent[0].content == \
            "✅ Exported **0** Top 25 lists and **1** Hall of Fame ballots for **2026**!"

    async def test_other_years_are_not_exported(self, admin_interaction, frozen_time):
        save_top_songs(1, "Old", "raw", "1. A // a", "", "", "", "")
        frozen_time("2027-03-01 12:00:00")

        await export_eoy_nominations.callback(admin_interaction)

        assert admin_interaction.sent[0].content == "No End of Year submissions found for 2027 yet!"

    async def test_the_reply_is_private(self, admin_interaction):
        save_hof_nomination(1, "Jo", "BTS")

        await export_eoy_nominations.callback(admin_interaction)

        admin_interaction.response.defer.assert_awaited_once_with(ephemeral=True)


class TestVotingHub:
    """/end-of-year-voting posts the ballot hub."""

    async def test_posts_the_voting_hub_and_explains_the_points(self, admin_interaction):
        await end_of_year_voting.callback(admin_interaction)

        [hub] = admin_interaction.channel.sent
        assert hub.embed.title == "2026 End of Year Voting is Live!"
        description = hub.embed.description
        assert "**2026 HallyU Music Awards** and the **2026 HallyU Hall of Fame**" in description
        assert "🥇 1st Choice = 3 Points" in description and "🥉 3rd Choice = 1 Point" in description
        assert isinstance(hub.kwargs["view"], EOYVotingHub)
        assert admin_interaction.sent[0].content == "End of Year Voting posted successfully!"
