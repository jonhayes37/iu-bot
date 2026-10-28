"""What every end of year button, form and ballot shares: refusing once the year's festivities are closed."""

import discord

from db.bot import EndOfYearPostKind, is_end_of_year_closed, record_end_of_year_post


def closed_message(year: int) -> str:
    """What members are told when they use an end of year button or form after /end-of-year-close."""
    return (f"🔒 The {year} end of year festivities are closed, so submissions and votes are no longer "
            "accepted. Thanks for taking part!")


async def refuse_if_closed(interaction: discord.Interaction, year: int) -> bool:
    """Tells the user (privately) and returns True if the year's festivities are closed."""
    if not is_end_of_year_closed(year):
        return False
    await interaction.response.send_message(closed_message(year), ephemeral=True)
    return True


async def post_hub(interaction: discord.Interaction, year: int, kind: EndOfYearPostKind,
                   embed: discord.Embed, view: discord.ui.View) -> bool:
    """
    Posts an end of year hub in the command's channel and remembers it, so /end-of-year-close can grey
    its buttons out. For a deferred admin command: refuses (and returns False) once the year is closed.
    """
    if is_end_of_year_closed(year):
        await interaction.followup.send(
            f"🔒 The {year} end of year festivities are closed (with `/end-of-year-close`), so nothing was posted.")
        return False

    message = await interaction.channel.send(embed=embed, view=view)
    record_end_of_year_post(year, kind, interaction.channel.id, message.id)
    return True
