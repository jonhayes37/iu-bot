"""Commands for the HMA nominations"""
import io
import re
import discord
from db.bot import EndOfYearPostKind
from db.hmas import (
    AddCategoryResult, MAX_CATEGORIES_PER_FAMILY, RemoveCategoryResult,
    add_category, get_active_hma_categories, get_yearly_export_data, remove_category,
    set_final_nominees, get_all_category_suggestions,
    get_current_categories_by_family
)
from ui.end_of_year import post_hub
from ui.hma_nominations import MAX_BOX_TITLE_LENGTH
from ui.hma_suggestions import HMASuggestionsHub
from utils.end_of_year import get_festivities_year
from utils.validation import admin_only, ballot_nominees_problem

# Category IDs are typed in commands and stored as menu values: short, lowercase, no spaces
CATEGORY_ID_PATTERN = re.compile(r"[a-z0-9_]{1,30}")
# A category's name is the title of its box on the nomination form, which shows at most 45 characters
MAX_CATEGORY_NAME_LENGTH = MAX_BOX_TITLE_LENGTH

FAMILY_CHOICES = [
    discord.app_commands.Choice(name="Daesang", value="daesang"),
    discord.app_commands.Choice(name="Bonsang", value="bonsang"),
    discord.app_commands.Choice(name="Fun", value="fun"),
]


async def active_category_autocomplete(_: discord.Interaction, current: str):
    """Suggests the active categories whose ID or name contains what the admin has typed."""
    typed = current.casefold()
    matches = [c for c in get_active_hma_categories()
               if typed in c['category_id'].casefold() or typed in c['name'].casefold()]
    return [discord.app_commands.Choice(name=f"{c['name']} ({c['category_id']})"[:100], value=c['category_id'])
            for c in matches[:25]]


@discord.app_commands.command(name='hma-nomination-export',
                              description="[Admin] Export all HMA nominations to a text file.")
@discord.app_commands.describe(year="The award year to export (defaults to this year's festivities)")
@admin_only
async def hma_nomination_export(interaction: discord.Interaction, year: int = None):
    """The Discord command logic for exporting the year's nominations."""
    # Uploading the file can take longer than the 3 seconds Discord allows for a first response
    await interaction.response.defer(ephemeral=True)

    # Fallback to current year if the admin didn't specify one
    target_year = year or get_festivities_year()

    data = get_yearly_export_data(target_year)

    if not data:
        await interaction.followup.send(f"No nominations found for the {target_year} awards yet.", ephemeral=True)
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

    await interaction.followup.send(
        content=f"Here is the organized raw data export for the **{target_year} HMAs**:",
        file=discord_file,
        ephemeral=True
    )


@discord.app_commands.command(name='hma-set-nominees', description="[Admin] Set the nominees for an award category.")
@discord.app_commands.describe(
    category_id="The category (start typing its name or ID, e.g. 'soty')",
    nominees_pipe="Pipe-separated list of nominees (e.g., 'IVE - HEYA | aespa - Supernova')"
)
@discord.app_commands.autocomplete(category_id=active_category_autocomplete)
@admin_only
async def hma_set_nominees(interaction: discord.Interaction, category_id: str, nominees_pipe: str):
    await interaction.response.defer(ephemeral=True)

    # Split by the pipe character and strip whitespace from both ends of each nominee
    nominees = [n.strip() for n in nominees_pipe.split('|') if n.strip()]

    if not nominees:
        await interaction.followup.send("❌ No valid nominees found. Check your formatting.")
        return

    problem = ballot_nominees_problem(nominees)
    if problem:
        await interaction.followup.send(problem)
        return

    year = get_festivities_year()
    if not set_final_nominees(year, category_id, nominees):
        await interaction.followup.send(
            f"❌ There is no active category called `{category_id}`. Pick one from the list as you type, "
            "or add it with `/add-hma-category`.")
        return

    # Format the output for a clean visual confirmation
    formatted_list = "\n".join([f"• {name}" for name in nominees])

    await interaction.followup.send(
        f"✅ **Saved {len(nominees)} nominees for `{category_id}` ({year})!**\n\n{formatted_list}"
    )

@discord.app_commands.command(name='end-of-year-hma-suggestions',
                              description="[Admin] Start the HMA category suggestions")
@admin_only
async def end_of_year_hma_suggestions(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    year = get_festivities_year()

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

    if await post_hub(interaction, year, EndOfYearPostKind.SUGGESTIONS, embed, HMASuggestionsHub(year)):
        await interaction.followup.send("HMA Category Suggestions posted!")


@discord.app_commands.command(name='add-hma-category', description="[Admin] Add an HMA award category.")
@discord.app_commands.describe(
    category_id="A short ID: lowercase letters, numbers and _ (e.g. 'best_ost'). Reuse a removed one's to restore it",
    family="Which group of awards it belongs to",
    name="The category's name, as members see it (e.g. 'Best OST')"
)
@discord.app_commands.choices(family=FAMILY_CHOICES)
@admin_only
async def add_hma_category(interaction: discord.Interaction, category_id: str,
                           family: discord.app_commands.Choice[str],
                           name: discord.app_commands.Range[str, 1, MAX_CATEGORY_NAME_LENGTH]):
    category_id = category_id.strip().lower()
    name = name.strip()
    if not CATEGORY_ID_PATTERN.fullmatch(category_id):
        await interaction.response.send_message(
            "❌ A category ID can only use lowercase letters, numbers and `_`, up to 30 characters "
            "(for example `best_ost`).", ephemeral=True)
        return

    result = add_category(category_id, family.value, name)
    messages = {
        AddCategoryResult.ADDED: f"✅ Added **{name}** (`{category_id}`) to the {family.name} awards.",
        AddCategoryResult.RESTORED: f"✅ Brought back `{category_id}` as **{name}** in the {family.name} awards. "
                                    "Its earlier nominations and votes are back with it.",
        AddCategoryResult.ALREADY_ACTIVE: f"❌ There is already an active category with the ID `{category_id}`.",
        AddCategoryResult.NAME_TAKEN: f"❌ There is already an active category called **{name}**.",
        AddCategoryResult.FAMILY_FULL: f"❌ The {family.name} awards already have {MAX_CATEGORIES_PER_FAMILY} "
                                       "categories, the most a nomination menu can show. Remove one first.",
    }
    text = messages[result]
    if result in (AddCategoryResult.ADDED, AddCategoryResult.RESTORED):
        text += ("\nIt now appears on the nomination forms and the voting ballot. Set its finalists with "
                 "`/hma-set-nominees` before voting opens.")
    await interaction.response.send_message(text, ephemeral=True)


@discord.app_commands.command(name='remove-hma-category', description="[Admin] Remove an HMA award category.")
@discord.app_commands.describe(category_id="The category to remove (start typing its name or ID)")
@discord.app_commands.autocomplete(category_id=active_category_autocomplete)
@admin_only
async def remove_hma_category(interaction: discord.Interaction, category_id: str):
    result = remove_category(category_id)
    messages = {
        RemoveCategoryResult.REMOVED: (
            f"✅ Removed `{category_id}`. It no longer appears on the nomination forms, the voting ballot or the "
            "results. Its nominations and votes are kept: `/add-hma-category` with the same ID brings it back."),
        RemoveCategoryResult.ALREADY_REMOVED: f"`{category_id}` was already removed, so nothing changed.",
        RemoveCategoryResult.NO_SUCH_CATEGORY: f"❌ There is no category called `{category_id}`.",
    }
    await interaction.response.send_message(messages[result], ephemeral=True)

@discord.app_commands.command(name='hma-suggestions-export', description="[Admin] Export all HMA category suggestions.")
@admin_only
async def hma_suggestions_export(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    year = get_festivities_year()
    suggestions = get_all_category_suggestions(year)

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
