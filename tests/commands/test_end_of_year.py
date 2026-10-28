"""Tests for commands/end_of_year.py: the nominations hub, the export and the voting hub."""

from unittest import mock

import discord
import pytest

from commands.end_of_year import (
    end_of_year_close, end_of_year_nominations, end_of_year_voting, export_eoy_nominations
)
from config import Database
from db.bot import (
    EndOfYearPostKind, close_end_of_year, get_end_of_year_posts, is_end_of_year_closed, record_end_of_year_post
)
from db.hall_of_fame import save_hof_nomination
from db.top_songs import save_top_songs
from ui.eoy_nominations import EOYNominationsHub
from ui.eoy_voting import EOYVotingHub
from ui.hma_suggestions import HMASuggestionsHub
from testsupport.fakes import make_guild, make_interaction
from testsupport.ui import button_labels


@pytest.fixture(autouse=True)
def _databases(databases, frozen_time):
    databases(Database.TOP_SONGS, Database.HALL_OF_FAME, Database.HMAS, Database.BOT)
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
        assert button_labels(hub.kwargs["view"]) == ["Submit 2026 Top 25 Songs", "2026 HallyU Hall of Fame",
                                                     "2026 HMA Nominations"]
        assert "**3. HallyU Music Awards:** Nominate as many as you like in each award category." \
            in hub.embed.description

    async def test_in_december_it_is_still_for_the_year_being_celebrated(self, admin_interaction, frozen_time):
        frozen_time("2026-12-02 12:00:00")

        await end_of_year_nominations.callback(admin_interaction)

        assert admin_interaction.channel.sent[0].embed.title == "2026 End of Year Nominations!"

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
        save_top_songs(2026, 1, "Jo", "raw", "1. A // a\n2. B // b", "", "raw", "1. X // x", "")
        save_top_songs(2026, 2, "Sam", "raw", "1. C // c", "", "", "", "")
        save_hof_nomination(2026, 1, "Jo", "BTS, Girls' Generation")

        await export_eoy_nominations.callback(admin_interaction)

        [reply] = admin_interaction.sent
        assert reply.content == "✅ Exported **2** Top 25 lists and **1** Hall of Fame ballots for **2026**!"
        files = _files(reply)
        assert files["top_25_2026.txt"] == "--- Jo ---\n1. A // a\n2. B // b\n\n--- Sam ---\n1. C // c\n\n"
        assert files["honourable_mentions_2026.txt"] == "--- Jo ---\n1. X // x\n\n"     # Sam left his blank
        assert files["hall_of_fame_2026.txt"] == "--- Jo ---\nBTS, Girls' Generation\n\n"

    async def test_a_file_is_only_attached_when_it_has_content(self, admin_interaction):
        save_hof_nomination(2026, 1, "Jo", "BTS")

        await export_eoy_nominations.callback(admin_interaction)

        assert list(_files(admin_interaction.sent[0])) == ["hall_of_fame_2026.txt"]
        assert admin_interaction.sent[0].content == \
            "✅ Exported **0** Top 25 lists and **1** Hall of Fame ballots for **2026**!"

    async def test_other_years_are_not_exported(self, admin_interaction):
        save_top_songs(2025, 1, "Old", "raw", "1. A // a", "", "", "", "")

        await export_eoy_nominations.callback(admin_interaction)

        assert admin_interaction.sent[0].content == "No End of Year submissions found for 2026 yet!"

    async def test_an_export_after_the_december_1_deadline_includes_the_november_submissions(
            self, admin_interaction, frozen_time):
        save_top_songs(2026, 1, "Jo", "raw", "1. A // a", "", "", "", "")
        frozen_time("2026-12-02 12:00:00")

        await export_eoy_nominations.callback(admin_interaction)

        assert admin_interaction.sent[0].content == \
            "✅ Exported **1** Top 25 lists and **0** Hall of Fame ballots for **2026**!"

    async def test_the_reply_is_private(self, admin_interaction):
        save_hof_nomination(2026, 1, "Jo", "BTS")

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

    async def test_voting_opened_in_december_is_for_the_year_being_celebrated(self, admin_interaction, frozen_time):
        frozen_time("2026-12-02 12:00:00")

        await end_of_year_voting.callback(admin_interaction)

        [hub] = admin_interaction.channel.sent
        assert hub.embed.title == "2026 End of Year Voting is Live!"
        assert button_labels(hub.kwargs["view"]) == ["2026 HallyU Hall of Fame", "2026 HallyU Music Awards"]


@pytest.mark.parametrize("command, kind", [
    (end_of_year_nominations, EndOfYearPostKind.NOMINATIONS), (end_of_year_voting, EndOfYearPostKind.VOTING)])
async def test_each_hub_is_remembered_so_it_can_be_closed(admin_interaction, command, kind):
    await command.callback(admin_interaction)

    [post] = get_end_of_year_posts(2026)
    assert (post.kind, post.channel_id) == (kind, admin_interaction.channel.id)


@pytest.mark.parametrize("command", [end_of_year_nominations, end_of_year_voting])
async def test_no_hub_is_posted_once_the_year_is_closed(admin_interaction, command):
    close_end_of_year(2026)

    await command.callback(admin_interaction)

    assert admin_interaction.channel.sent == []
    assert get_end_of_year_posts(2026) == []
    assert admin_interaction.sent[0].content == (
        "🔒 The 2026 end of year festivities are closed (with `/end-of-year-close`), so nothing was posted.")


class TestClose:
    """/end-of-year-close closes the year and greys out every hub's buttons."""

    @pytest.fixture(name="server")
    def _server(self, frozen_time):
        frozen_time("2026-12-12 12:00:00")
        guild = make_guild(channels=("announcements", "private"))
        return guild, make_interaction(guild=guild, channel=guild.text_channels[0], administrator=True)

    @staticmethod
    def _post(channel, kind, message_id, year=2026):
        record_end_of_year_post(year, kind, channel.id, message_id)
        message = mock.MagicMock(spec=discord.Message)
        message.edit = mock.AsyncMock()
        return message

    @staticmethod
    def _messages(channel, by_id):
        channel.fetch_message = mock.AsyncMock(side_effect=lambda message_id: by_id[message_id])

    async def test_closes_the_year_and_greys_out_every_hub(self, server):
        guild, interaction = server
        announcements, private = guild.text_channels
        suggestions = self._post(announcements, EndOfYearPostKind.SUGGESTIONS, 1)
        voting = self._post(announcements, EndOfYearPostKind.VOTING, 2)
        nominations = self._post(private, EndOfYearPostKind.NOMINATIONS, 3)
        self._messages(announcements, {1: suggestions, 2: voting})
        self._messages(private, {3: nominations})

        await end_of_year_close.callback(interaction)

        assert is_end_of_year_closed(2026)
        for message, hub in ((suggestions, HMASuggestionsHub), (voting, EOYVotingHub),
                             (nominations, EOYNominationsHub)):
            view = message.edit.await_args.kwargs["view"]
            assert isinstance(view, hub)
            assert all(button.item.disabled for button in view.children)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        assert interaction.sent[0].content == (
            "🔒 The **2026** end of year festivities are closed.\n"
            "Anyone who presses an old button or sends a form is told they're closed.\n"
            "Buttons greyed out on **3** posts.\n"
            "Run `/end-of-year-results` for the winners.")

    async def test_only_this_years_posts_are_touched(self, server):
        guild, interaction = server
        [announcements, _] = guild.text_channels
        old = self._post(announcements, EndOfYearPostKind.VOTING, 1, year=2025)
        self._messages(announcements, {1: old})

        await end_of_year_close.callback(interaction)

        old.edit.assert_not_awaited()
        assert "Buttons greyed out on **0** posts." in interaction.sent[0].content
        assert not is_end_of_year_closed(2025)

    async def test_deleted_posts_and_channels_are_counted_not_fatal(self, server):
        guild, interaction = server
        announcements, _ = guild.text_channels
        kept = self._post(announcements, EndOfYearPostKind.VOTING, 1)
        self._post(announcements, EndOfYearPostKind.NOMINATIONS, 2)
        record_end_of_year_post(2026, EndOfYearPostKind.SUGGESTIONS, 999, 3)       # a channel since deleted
        async def fetch(message_id):
            if message_id == 1:
                return kept
            raise discord.NotFound(mock.Mock(status=404, reason="Not Found"), "Unknown Message")
        announcements.fetch_message = mock.AsyncMock(side_effect=fetch)

        await end_of_year_close.callback(interaction)

        kept.edit.assert_awaited_once()
        content = interaction.sent[0].content
        assert "Buttons greyed out on **1** post.\n2 had already been deleted." in content

    async def test_a_post_that_cannot_be_edited_is_reported(self, server):
        guild, interaction = server
        announcements, _ = guild.text_channels
        message = self._post(announcements, EndOfYearPostKind.VOTING, 1)
        message.edit.side_effect = discord.Forbidden(mock.Mock(status=403, reason="Forbidden"), "Missing Access")
        self._messages(announcements, {1: message})

        await end_of_year_close.callback(interaction)

        content = interaction.sent[0].content
        assert "⚠️ 1 couldn't be edited (check IU can still see that channel). Their buttons refuse anyway." \
            in content
        assert is_end_of_year_closed(2026)

    async def test_closing_again_says_so_and_greys_out_any_new_post(self, server):
        guild, interaction = server
        announcements, _ = guild.text_channels
        close_end_of_year(2026)
        message = self._post(announcements, EndOfYearPostKind.VOTING, 1)
        self._messages(announcements, {1: message})

        await end_of_year_close.callback(interaction)

        assert interaction.sent[0].content.startswith("🔒 The **2026** end of year festivities were already closed.")
        message.edit.assert_awaited_once()

    async def test_run_outside_a_server_it_still_closes_the_year(self, admin_interaction):
        record_end_of_year_post(2026, EndOfYearPostKind.VOTING, 5, 1)

        await end_of_year_close.callback(admin_interaction)

        assert is_end_of_year_closed(2026)
        assert "1 had already been deleted." in admin_interaction.sent[0].content
