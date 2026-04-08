"""Commands for the HMA nominations"""
import io
import discord
from db.hmas import (
    get_family_choices, get_yearly_export_data,
    set_final_nominees, get_all_category_suggestions,
    get_current_categories_by_family
)
from ui.hma_nominations import MultiNominationView
from ui.hma_suggestions import HMASuggestionsHub
from utils.end_of_year import get_current_award_year


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


@discord.app_commands.command(name='hma-set-nominees', description="[Admin] Set the nominees for an award category.")
@discord.app_commands.describe(
    category_id="The ID of the category (e.g., 'soty')",
    nominees_pipe="Pipe-separated list of nominees (e.g., 'IVE - HEYA | aespa - Supernova')"
)
@discord.app_commands.default_permissions(administrator=True)
async def hma_set_nominees(interaction: discord.Interaction, category_id: str, nominees_pipe: str):
    await interaction.response.defer(ephemeral=True)

    # Split by the pipe character and strip whitespace from both ends of each nominee
    nominees = [n.strip() for n in nominees_pipe.split('|') if n.strip()]

    if not nominees:
        await interaction.followup.send("❌ No valid nominees found. Check your formatting.")
        return

    try:
        year = set_final_nominees(category_id, nominees)

        # Format the output for a clean visual confirmation
        formatted_list = "\n".join([f"• {name}" for name in nominees])

        await interaction.followup.send(
            f"✅ **Saved {len(nominees)} nominees for `{category_id}` ({year})!**\n\n{formatted_list}"
        )

    except Exception as e:
        await interaction.followup.send(f"❌ Database error: {e}")

@discord.app_commands.command(name='end-of-year-hma-suggestions',
                              description="[Admin] Start the HMA category suggestions")
@discord.app_commands.default_permissions(administrator=True)
async def end_of_year_hma_suggestions(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    year = get_current_award_year()

    # Fetch and format the current awards
    categories_by_family = get_current_categories_by_family()
    awards_text = ""
    for family, cats in categories_by_family.items():
        awards_text += f"**{family}**\n"
        awards_text += " • " + "\n • ".join(cats) + "\n\n"

    # Fallback just in case the DB is empty
    if not awards_text:
        awards_text = "*No categories currently seeded in the database.*"

    # Build the embed with the dynamic text
    embed = discord.Embed(
        title=f"💡 {year} HMA Category Suggestions",
        description=(
            f"This is for submitting award **categories - not nominees** - for the {year} HallyU Music Awards. "
            "If there's a new category you think we should try or one we should drop, please click the button "
            "below to submit your ideas!\n\n"
            f"__**Current Awards:**__\n\n{awards_text}"
        ),
        color=discord.Color.orange()
    )

    await interaction.channel.send(embed=embed, view=HMASuggestionsHub(year))
    await interaction.followup.send("HMA Category Suggestions posted!")

@discord.app_commands.command(name='hma-suggestions-export', description="[Admin] Export all HMA category suggestions.")
@discord.app_commands.default_permissions(administrator=True)
async def hma_suggestions_export(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    year = get_current_award_year()
    suggestions = get_all_category_suggestions()

    if not suggestions:
        await interaction.followup.send("No suggestions have been submitted yet.")
        return

    buffer = io.StringIO()
    buffer.write(f"HMA CATEGORY SUGGESTIONS ({year})\n")
    buffer.write("="*40 + "\n\n")

    for sub in suggestions:
        buffer.write(f"--- {sub['username']} ---\n")
        if sub['new_categories']:
            buffer.write(f"ADD:\n{sub['new_categories']}\n\n")
        if sub['dropped_categories']:
            buffer.write(f"DROP/MERGE:\n{sub['dropped_categories']}\n\n")
        buffer.write("\n")

    file = discord.File(
        fp=io.BytesIO(buffer.getvalue().encode('utf-8')),
        filename=f"{year}_hma_suggestions.txt"
    )

    await interaction.followup.send(
        content=f"✅ Exported **{len(suggestions)}** community suggestions!",
        file=file
    )
