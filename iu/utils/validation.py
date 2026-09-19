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
            line = re.sub(r'\s*\(\s*https?://[^\s()]+\s*\)\s*', '', line)
            line = re.sub(r'\s*https?://[^\s()]+\s*', '', line)
        else:
            extracted_urls.append("")

        line = re.sub(r'\s*//\s*', ' // ', line)

        if ' // ' not in line:
            line = re.sub(r'\s+[-/]\s+', ' // ', line, count=1)

        # Only strip a real list marker ("1.", "1)", "1 -"), not 2NE1, 2PM, etc.
        line = re.sub(r'^\d+\s*(?:[.)](?!\d)|-(?=\s))\s*', '', line)
        cleaned_lines.append(f"{i}. {line}")

    return True, "", "\n".join(cleaned_lines), ",".join(extracted_urls)
