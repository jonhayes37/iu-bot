"""Commands for the hall of fame"""
import discord
from db.hall_of_fame import (
    Inductee, add_hall_of_famer as add_hall_of_famer_db, add_lifetime_achiever as add_lifetime_achiever_db,
    find_hall_of_famer, find_lifetime_achiever, set_hof_final_nominees
)
from utils.end_of_year import get_festivities_year
from utils.validation import admin_only, ballot_nominees_problem

# Long enough for any act's name, short enough to list many of them on the nominations form
MAX_INDUCTEE_NAME_LENGTH = 100

@discord.app_commands.command(name='hall-of-fame-set-nominees',
                              description="[Admin] Set the shortlist of nominees for the Hall of Fame.")
@discord.app_commands.describe(
    nominees_pipe="Pipe-separated list of nominees (e.g., 'BTS | Girls Generation | Seventeen')"
)
@admin_only
async def hall_of_fame_set_nominees(interaction: discord.Interaction, nominees_pipe: str):
    await interaction.response.defer(ephemeral=True)

    # Split by the pipe character and strip whitespace
    nominees = [n.strip() for n in nominees_pipe.split('|') if n.strip()]
    if not nominees:
        await interaction.followup.send("❌ No valid nominees found. Check your formatting.")
        return

    problem = ballot_nominees_problem(nominees)
    if problem:
        await interaction.followup.send(problem)
        return

    year = get_festivities_year()
    set_hof_final_nominees(year, nominees)
    formatted_list = "\n".join([f"• {name}" for name in nominees])
    await interaction.followup.send(
        f"✅ **Saved {len(nominees)} Hall of Fame nominees for {year}!**\n\n{formatted_list}"
    )


@discord.app_commands.command(name='add-hall-of-famer',
                              description="[Admin] Induct someone into the Hall of Fame this year.")
@discord.app_commands.describe(name="Who was inducted (e.g. 'Girls' Generation')")
@admin_only
async def add_hall_of_famer(interaction: discord.Interaction,
                            name: discord.app_commands.Range[str, 1, MAX_INDUCTEE_NAME_LENGTH]):
    year = get_festivities_year()
    name = name.strip()
    if not name:
        await interaction.response.send_message("❌ The name can't be blank.", ephemeral=True)
        return

    if add_hall_of_famer_db(name, year):
        await interaction.response.send_message(f"🏛️ **{name}** is in the Hall of Fame (class of {year}).",
                                                ephemeral=True)
    else:
        await _already_in(interaction, find_hall_of_famer(name), "in the Hall of Fame")


@discord.app_commands.command(name='add-lifetime-achiever',
                              description="[Admin] Give someone this year's lifetime achievement award.")
@discord.app_commands.describe(name="Who receives the award")
@admin_only
async def add_lifetime_achiever(interaction: discord.Interaction,
                                name: discord.app_commands.Range[str, 1, MAX_INDUCTEE_NAME_LENGTH]):
    year = get_festivities_year()
    name = name.strip()
    if not name:
        await interaction.response.send_message("❌ The name can't be blank.", ephemeral=True)
        return

    if add_lifetime_achiever_db(name, year):
        await interaction.response.send_message(f"🌟 **{name}** has the lifetime achievement award ({year}).",
                                                ephemeral=True)
    else:
        await _already_in(interaction, find_lifetime_achiever(name), "a lifetime achievement award winner")


async def _already_in(interaction: discord.Interaction, existing: Inductee, where: str):
    await interaction.response.send_message(
        f"ℹ️ **{existing.name}** is already {where} (since {existing.year_inducted}), so nothing changed.",
        ephemeral=True)
