"""Validation helpers"""
import re
import discord
from discord import app_commands

def admin_only(command):
    """
    Restricts a slash command to server administrators. Apply directly beneath the @command decorator.

    default_permissions only sets what the Discord UI offers by default; a server admin can override
    it under Server Settings > Integrations, and the bot never sees that. The check makes the bot
    enforce it on every call, whatever the UI says.
    """
    command = app_commands.checks.has_permissions(administrator=True)(command)
    return app_commands.default_permissions(administrator=True)(command)

async def validate_channel(interaction: discord.Interaction, channel: str) -> bool:
    if interaction.channel.name != channel:
        await interaction.response.send_message(
            f"This command can only be used in the #{channel} channel.",
            ephemeral=True
        )
        return True

    return False


_HEX_COLOUR = re.compile(r'(?:#|0x)?([0-9a-f]{1,6})', re.IGNORECASE)


def parse_colour(text: str) -> int | None:
    """
    Turns "ff4980", "#ff4980" or "0xff4980" into an embed colour. Returns None if it isn't a hex colour
    from 0 to ffffff (Discord rejects anything bigger when the embed is shown).
    """
    match = _HEX_COLOUR.fullmatch(text.strip())
    return int(match.group(1), 16) if match else None


# A voting ballot is three select menus that each list every nominee. Discord allows 25 options per
# menu and 100 characters per option, and voters must rank three different nominees.
MIN_BALLOT_NOMINEES = 3
MAX_BALLOT_NOMINEES = 25
MAX_BALLOT_NOMINEE_LENGTH = 100


def ballot_nominees_problem(nominees: list[str]) -> str | None:
    """
    Why this list of nominees couldn't be shown on a voting ballot, as a message for the admin, or
    None if it can. Checked when the nominees are set, so a bad list never reaches the voters.
    """
    if len(nominees) < MIN_BALLOT_NOMINEES:
        return (f"❌ You gave {len(nominees)} nominee{'s' if len(nominees) != 1 else ''}, but voters rank "
                f"their top {MIN_BALLOT_NOMINEES}, so a ballot needs at least {MIN_BALLOT_NOMINEES}.")

    if len(nominees) > MAX_BALLOT_NOMINEES:
        return (f"❌ You gave {len(nominees)} nominees, but a voting menu holds at most "
                f"{MAX_BALLOT_NOMINEES}. Shorten the list and try again.")

    if len(set(nominees)) != len(nominees):
        return "❌ The list has the same nominee more than once."

    too_long = [name for name in nominees if len(name) > MAX_BALLOT_NOMINEE_LENGTH]
    if too_long:
        examples = "\n".join(f"• {name[:MAX_BALLOT_NOMINEE_LENGTH]}… ({len(name)} characters)"
                             for name in too_long[:5])
        return (f"❌ A voting menu shows at most {MAX_BALLOT_NOMINEE_LENGTH} characters per nominee. "
                f"Shorten these:\n{examples}")

    return None


def sanitize_list(raw_text: str, expected_count: int) -> tuple[bool, str, str, str]:
    """
    Parses the raw modal text for Top 25 and HMs.
    Returns: (is_valid, error_msg, cleaned_text, comma_separated_urls)
    """
    if not raw_text.strip():
        return True, "", "", ""

    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

    # Hard validation: Check the line count
    if len(lines) != expected_count:
        return False, f"Your main list requires exactly {expected_count} songs, but you provided {len(lines)}.", "", ""

    cleaned_lines = []
    extracted_urls = []
    for i, line in enumerate(lines, start=1):
        url_match = re.search(r'(https?://[^\s()]+)', line)
        if url_match:
            url = url_match.group(1)
            extracted_urls.append(url)
            # Replace the link with a space (not nothing) so the words either side don't run together
            line = re.sub(r'\s*\(\s*https?://[^\s()]+\s*\)\s*', ' ', line)
            line = re.sub(r'\s*https?://[^\s()]+\s*', ' ', line).strip()
        else:
            extracted_urls.append("")

        # Only strip a real list marker ("1.", "1)", "1 -"), not 2NE1, 2PM, etc. This comes before the
        # separator is rewritten, or a "1 - Artist - Title" line would lose its marker to the wrong dash.
        line = re.sub(r'^\d+\s*(?:[.)](?!\d)|-(?=\s))\s*', '', line)

        line = re.sub(r'\s*//\s*', ' // ', line)

        if ' // ' not in line:
            line = re.sub(r'\s+[-/]\s+', ' // ', line, count=1)

        cleaned_lines.append(f"{i}. {line}")

    return True, "", "\n".join(cleaned_lines), ",".join(extracted_urls)
