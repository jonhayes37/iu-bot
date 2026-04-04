"""Commands for the HMA nominations"""
import io
import discord
from db.hma_nominations import (
    add_nomination, get_family_choices,
    get_yearly_export_data, get_current_award_year
)
from services.youtube import contains_youtube_url


def build_dropdown(family_id: str) -> list[discord.app_commands.Choice[str]]:
    """Helper function to fetch DB rows and convert them to Discord Choices."""
    items = get_family_choices(family_id)
    # Discord enforces a strict hard limit of 25 choices per dropdown.
    # We slice [:25] just in case the DB ever exceeds it, preventing a bot crash.
    return [discord.app_commands.Choice(name=name, value=cat_id) for cat_id, name in items][:25]


@discord.app_commands.command(name='hma-nomination', description="Submit a nomination for the HallyU Music Awards!")
@discord.app_commands.describe(
    nominee="Who or what are you nominating? (e.g., 'IVE - HEYA', a YouTube link)",
    daesang="Daesang Awards (Optional)",
    bonsang="Bonsang Awards (Optional)",
    fun="Fun Awards (Optional)"
)
@discord.app_commands.choices(
    # These functions run once when the bot boots up!
    daesang=build_dropdown('daesang'),
    bonsang=build_dropdown('bonsang'),
    fun=build_dropdown('fun')
)
async def hma_nomination(
    interaction: discord.Interaction,
    nominee: str,
    daesang: discord.app_commands.Choice[str] = None,
    bonsang: discord.app_commands.Choice[str] = None,
    fun: discord.app_commands.Choice[str] = None
):
    """The Discord command logic for multi-category HMA nominations."""

    # Validation: Ensure they picked at least one category
    selected_categories = [cat for cat in (daesang, bonsang, fun) if cat is not None]
    if not selected_categories:
        await interaction.response.send_message(
            "❌ You must select at least one award category from the dropdowns to submit your nomination!", 
            ephemeral=True
        )
        return

    # Validate a YouTube URL exists for covers
    cover_category_ids = {'best_vocal_cover', 'best_dance_cover'}
    requires_url = any(cat.value in cover_category_ids for cat in selected_categories)
    if requires_url:
        if contains_youtube_url(nominee):
            await interaction.response.send_message(
                "❌ Nominations for **Best Vocal Cover** and **Best Dance Cover** must include a valid YouTube link!", 
                ephemeral=True
            )
            return

    # Process the nominations
    try:
        award_year = None
        category_names = []

        # Loop through whatever they selected and add a database row for each
        for category in selected_categories:
            award_year = add_nomination(interaction.user.id, category.value, nominee)
            category_names.append(f"• {category.name}")

    except Exception as ex:
        await interaction.response.send_message(f"❌ Database error: {ex}", ephemeral=True)
        return

    # Format the confirmation message
    formatted_categories = "\n".join(category_names)

    embed = discord.Embed(
        title="🏆 Nomination Submitted!",
        description=f"Your nomination for the **{award_year} HallyU Music Awards** has been recorded.",
        color=discord.Color.gold()
    )
    embed.add_field(name="Nominee", value=f"**{nominee}**", inline=False)
    embed.add_field(name="Categories", value=formatted_categories, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

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
