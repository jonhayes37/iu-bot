"""Commands for the HMA nominations"""
import io
import discord
from db.hma_nominations import (
    get_family_choices, get_yearly_export_data, get_current_award_year
)
from ui.hma_nominations import MultiNominationView


def build_dropdown(family_id: str) -> list[discord.app_commands.Choice[str]]:
    """Helper function to fetch DB rows and convert them to Discord Choices."""
    items = get_family_choices(family_id)
    # Discord enforces a strict hard limit of 25 choices per dropdown.
    # We slice [:25] just in case the DB ever exceeds it, preventing a bot crash.
    return [discord.app_commands.Choice(name=name, value=cat_id) for cat_id, name in items][:25]

@discord.app_commands.command(name='hma-nomination', description="Submit a nomination for the HallyU Music Awards!")
@discord.app_commands.describe(
    nominee="Who or what are you nominating? (e.g., 'IVE - HEYA', a YouTube link)"
)
async def hma_nomination(interaction: discord.Interaction, nominee: str):
    """The Discord command logic for multi-category HMA nominations."""

    view = MultiNominationView(nominee)
    msg = f"Nominating **{nominee}**\nSelect all award categories below:"
    await interaction.response.send_message(content=msg, view=view, ephemeral=True)

@discord.app_commands.command(name='hma-nomination-export',
                              description="[Admin] Export all HMA nominations to a text file.")
@discord.app_commands.describe(year="The award year to export (defaults to the current active year)")
@discord.app_commands.default_permissions(administrator=True)
async def hma_nomination_export(interaction: discord.Interaction, year: int = None):
    """The Discord command logic for exporting the year's nominations."""

    # Fallback to current year if the admin didn't specify one
    target_year = year or get_current_award_year()

    try:
        data = get_yearly_export_data(target_year)
    except Exception as ex:
        await interaction.response.send_message(f"❌ Database error: {ex}", ephemeral=True)
        return

    if not data:
        await interaction.response.send_message(
            f"No nominations found for the {target_year} awards yet.",
            ephemeral=True
        )
        return

    # Build the text file content string
    lines = [f"🏆 HallyU Music Awards - {target_year} Nominations 🏆", "=" * 50, ""]

    # Unpack the nested dictionary: Family -> Category -> List of Nominations
    for family_name, categories in data.items():
        lines.append(f"████ {family_name.upper()} ████")
        lines.append("")

        for cat_name, nominations in categories.items():
            lines.append(f"### {cat_name} ###")
            for u_id, text in nominations:
                # Storing the Discord ID is helpful to trace troll links back to the user
                lines.append(f"- {text} (Submitted by ID: {u_id})")
            lines.append("")

        lines.append("-" * 50)
        lines.append("")

    file_content = "\n".join(lines)

    # Convert the string into a byte stream so Discord can send it as a file attachment
    file_bytes = io.BytesIO(file_content.encode('utf-8'))
    discord_file = discord.File(fp=file_bytes, filename=f"{target_year}_hma_nominations.txt")

    await interaction.response.send_message(
        content=f"Here is the organized raw data export for the **{target_year} HMAs**:",
        file=discord_file,
        ephemeral=True
    )
