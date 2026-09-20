"""Tests for utils/validation.py"""

import discord
import pytest
from discord import app_commands

from config import Channel
from utils.validation import admin_only, parse_colour, sanitize_list, validate_channel


def _admin_command():
    """A command declared the way the real ones are: @command on top, @admin_only directly beneath."""
    @app_commands.command(name="secret", description="Admins only")
    @admin_only
    async def secret(interaction: discord.Interaction):
        await interaction.response.send_message("ran")

    return secret


async def _run_checks(command, interaction) -> bool:
    """Runs a command's checks the way discord.py does (a check may be a plain function or a coroutine)."""
    for check in command.checks:
        if not await discord.utils.maybe_coroutine(check, interaction):
            return False
    return True


class TestAdminOnly:
    """admin_only hides a command by default and enforces it on every call."""

    def test_hides_the_command_from_non_admins_by_default(self):
        command = _admin_command()

        assert command.default_permissions == discord.Permissions(administrator=True)

    async def test_lets_an_administrator_through(self, make_interaction):
        command = _admin_command()
        interaction = make_interaction(administrator=True)

        assert await _run_checks(command, interaction)

    async def test_rejects_everyone_else_at_run_time(self, make_interaction):
        # The UI default can be overridden by a server admin in Integrations, so the bot checks itself
        command = _admin_command()
        interaction = make_interaction(administrator=False)

        with pytest.raises(app_commands.MissingPermissions) as caught:
            await _run_checks(command, interaction)

        assert caught.value.missing_permissions == ["administrator"]

    async def test_other_permissions_do_not_count(self, make_interaction):
        command = _admin_command()
        interaction = make_interaction()
        interaction.permissions = discord.Permissions(manage_guild=True, manage_roles=True)

        with pytest.raises(app_commands.MissingPermissions):
            await _run_checks(command, interaction)


class TestValidateChannel:
    """validate_channel returns True when it has already rejected the user."""

    async def test_right_channel_returns_false_and_sends_nothing(self, make_interaction):
        interaction = make_interaction(channel=Channel.MERCH_BOOTH)

        rejected = await validate_channel(interaction, Channel.MERCH_BOOTH)

        assert rejected is False
        assert interaction.sent == []

    async def test_wrong_channel_returns_true_and_tells_the_user_privately(self, make_interaction):
        interaction = make_interaction(channel="general")

        rejected = await validate_channel(interaction, Channel.MERCH_BOOTH)

        assert rejected is True
        [reply] = interaction.sent
        assert reply.content == "This command can only be used in the #merch-booth channel."
        assert reply.ephemeral

    async def test_channel_names_must_match_exactly(self, make_interaction):
        interaction = make_interaction(channel="Merch-Booth")

        assert await validate_channel(interaction, Channel.MERCH_BOOTH) is True


class TestParseColour:
    """parse_colour accepts hex colours Discord can display and nothing else."""

    @pytest.mark.parametrize("text, expected", [
        ("ff4980", 0xFF4980),
        ("FF4980", 0xFF4980),
        ("#ff4980", 0xFF4980),
        ("0xff4980", 0xFF4980),
        ("0XFF4980", 0xFF4980),
        ("  #ff4980  ", 0xFF4980),
        ("ffffff", 0xFFFFFF),        # the largest colour Discord accepts
        ("000000", 0),
        ("0", 0),
        ("fff", 0xFFF),              # short values are read as the number they spell, not expanded
    ])
    def test_valid_colours(self, text, expected):
        assert parse_colour(text) == expected

    @pytest.mark.parametrize("text", [
        "1000000",      # one above ffffff: Discord rejects it when the embed is shown
        "fffffff",
        "gggggg",
        "ff 49 80",
        "#",
        "0x",
        "",
        "   ",
        "-ff4980",
        "##ff4980",
        "red",
    ])
    def test_invalid_colours(self, text):
        assert parse_colour(text) is None


class TestSanitizeList:
    """sanitize_list cleans the Top 25 / honourable mention text a user pastes into the form."""

    def test_blank_input_is_valid_and_empty(self):
        # A blank form field means "no list", whatever count was expected
        assert sanitize_list("", 25) == (True, "", "", "")
        assert sanitize_list("  \n \n\t", 25) == (True, "", "", "")

    @pytest.mark.parametrize("raw, count, provided", [
        ("a\nb", 3, 2),
        ("a\nb\nc\nd", 3, 4),
        ("a", 3, 1),
    ])
    def test_wrong_number_of_songs_is_rejected(self, raw, count, provided):
        is_valid, error, cleaned, urls = sanitize_list(raw, count)

        assert not is_valid
        assert f"exactly {count} songs, but you provided {provided}" in error
        assert (cleaned, urls) == ("", "")

    def test_blank_lines_do_not_count_as_songs(self):
        assert sanitize_list("\n\nA - B\n\n\nC - D\n", 2) == (True, "", "1. A // B\n2. C // D", ",")

    def test_windows_line_endings(self):
        assert sanitize_list("IU - A\r\nB - C\r\n", 2)[2] == "1. IU // A\n2. B // C"

    def test_lines_are_numbered_from_one(self):
        cleaned = sanitize_list("A // a\nB // b\nC // c", 3)[2]

        assert cleaned.splitlines() == ["1. A // a", "2. B // b", "3. C // c"]

    @pytest.mark.parametrize("line, expected", [
        ("IU - Good Day", "IU // Good Day"),          # spaced dash becomes the artist/title separator
        ("BTS / Dynamite", "BTS // Dynamite"),        # so does a spaced slash
        ("IU//Good Day", "IU // Good Day"),           # a double slash is normalised to " // "
        ("IU   //   Good Day", "IU // Good Day"),
        ("IU // Good Day", "IU // Good Day"),
        ("IU - Good Day - Live", "IU // Good Day - Live"),   # only the first dash is the separator
        ("IU // A - B", "IU // A - B"),                # an existing // wins over dashes
        ("IU - a / b", "IU // a / b"),
        ("IU-Good Day", "IU-Good Day"),               # an unspaced dash is part of a name
        ("Just a title", "Just a title"),
    ])
    def test_artist_title_separator(self, line, expected):
        assert sanitize_list(line, 1)[2] == f"1. {expected}"

    @pytest.mark.parametrize("line, expected", [
        ("1. IU - X", "IU // X"),
        ("10. IU - X", "IU // X"),
        ("2) IU - X", "IU // X"),
        ("12)IU - X", "IU // X"),
    ])
    def test_existing_list_numbers_are_replaced(self, line, expected):
        assert sanitize_list(line, 1)[2] == f"1. {expected}"

    @pytest.mark.parametrize("line", [
        "2NE1 - Fire",
        "2PM - Heartbeat",
        "1.5 Something",
        "1 IU - X",
    ])
    def test_a_leading_number_that_is_part_of_the_name_is_kept(self, line):
        cleaned = sanitize_list(line, 1)[2]

        assert cleaned.startswith("1. ") and cleaned[3:].startswith(line[0])

    def test_urls_are_pulled_out_of_the_text(self):
        raw = "IU - Good Day (https://youtu.be/abc)\nBTS - Dynamite https://youtu.be/def\nplain - one"

        is_valid, _, cleaned, urls = sanitize_list(raw, 3)

        assert is_valid
        assert cleaned == "1. IU // Good Day\n2. BTS // Dynamite\n3. plain // one"
        # One entry per line, in order; a line without a link leaves its slot empty
        assert urls == "https://youtu.be/abc,https://youtu.be/def,"

    def test_urls_keep_their_query_string(self):
        _, _, cleaned, urls = sanitize_list("IU - Song (https://a.com/watch?v=1&t=5)", 1)

        assert cleaned == "1. IU // Song"
        assert urls == "https://a.com/watch?v=1&t=5"

    def test_only_the_first_url_on_a_line_is_kept(self):
        _, _, _, urls = sanitize_list("IU - Song https://a.com/1 https://a.com/2", 1)

        assert urls == "https://a.com/1"

    def test_a_line_that_is_only_a_url_leaves_an_empty_title(self):
        _, _, cleaned, urls = sanitize_list("https://youtu.be/abc", 1)

        assert cleaned == "1. "
        assert urls == "https://youtu.be/abc"

    @pytest.mark.parametrize("line, expected", [
        ("1 - IU - Good Day", "IU // Good Day"),
        ("2 - BTS - Dynamite - Live", "BTS // Dynamite - Live"),   # only the first remaining dash separates
        ("3 - Aespa // Next Level", "Aespa // Next Level"),
        ("4 - Just a title", "Just a title"),
    ])
    def test_dash_style_list_numbers_are_replaced(self, line, expected):
        # The number is dropped before the artist/title dash is looked for, so the wrong dash isn't used
        assert sanitize_list(line, 1)[2] == f"1. {expected}"

    @pytest.mark.parametrize("line, expected", [
        ("Song https://a.com (live)", "Song (live)"),
        ("IU - Song(https://a.com)Live", "IU // Song Live"),
        ("Before https://a.com after", "Before after"),
        ("IU - Song https://a.com", "IU // Song"),                  # a trailing link leaves no trailing space
        ("https://a.com IU - Song", "IU // Song"),                  # nor does a leading one leave a leading space
        ("(https://a.com) IU - Song", "IU // Song"),
    ])
    def test_removing_a_url_keeps_the_words_around_it_apart(self, line, expected):
        assert sanitize_list(line, 1)[2] == f"1. {expected}"
