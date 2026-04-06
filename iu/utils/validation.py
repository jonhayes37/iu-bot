"""Validation helpers"""
import re
import discord

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

        if ' // ' not in line and ' - ' in line:
            line = line.replace(' - ', ' // ', 1)

        line = re.sub(r'^\d+[\.\)\-]?\s*', '', line)
        cleaned_lines.append(f"{i}. {line}")

    return True, "", "\n".join(cleaned_lines), ",".join(extracted_urls)
