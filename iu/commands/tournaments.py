"""Discord slash commands for managing and interacting with bracket tournaments."""

import asyncio
import discord
from config import Channel
from db.tournaments import create_tournament, force_close_active_round
from ui.bracket_renderer import generate_bracket_image
from tasks.tournaments import post_round_polls

# Discord's limits for a poll: 55 characters per answer, and a poll can run for at most 32 days
MAX_ENTRANT_NAME_LENGTH = 55
MAX_DAYS_PER_ROUND = 32

@discord.app_commands.command(name="new-tournament", description="[Admin] Creates a new bracket tournament.")
@discord.app_commands.describe(
    title="The name of the tournament",
    description="A short description of the tournament's theme or rules.",
    entrants="Pipe-separated list of tracks, ordered from seed #1 to the lowest seed.",
    days_per_round="How long each voting round lasts (default 2)"
)
@discord.app_commands.default_permissions(administrator=True)
async def new_tournament(interaction: discord.Interaction, title: str, description: str,
                         entrants: str, days_per_round: int = 2):
    await interaction.response.defer(ephemeral=True)

    # Parse and validate entrants
    entrants = [e.strip() for e in entrants.split('|') if e.strip()]
    num_entrants = len(entrants)

    # Minimum size check
    if num_entrants < 4:
        await interaction.followup.send("You need at least 4 tracks to run a bracket!", ephemeral=True)
        return

    # Bitwise Power-of-Two check
    if (num_entrants & (num_entrants - 1)) != 0:
        await interaction.followup.send(
            f"Tournaments require a power of two (4, 8, 16, 32), but you provided **{num_entrants}**."
        )
        return

    if not 1 <= days_per_round <= MAX_DAYS_PER_ROUND:
        await interaction.followup.send(
            f"Each round must last between 1 and {MAX_DAYS_PER_ROUND} days (Discord's poll limit), "
            f"but you asked for **{days_per_round}**."
        )
        return

    too_long = [name for name in entrants if len(name) > MAX_ENTRANT_NAME_LENGTH]
    if too_long:
        examples = "\n".join(f"• {name} ({len(name)} characters)" for name in too_long[:5])
        await interaction.followup.send(
            f"Discord polls only allow {MAX_ENTRANT_NAME_LENGTH} characters per entrant. "
            f"Please shorten these:\n{examples}"
        )
        return

    # Check where the polls will go before creating anything
    tournaments_channel = discord.utils.get(interaction.guild.text_channels, name=Channel.TOURNAMENTS)
    if not tournaments_channel:
        await interaction.followup.send(f"I can't find the #{Channel.TOURNAMENTS} channel, so nothing was created.")
        return

    # Create the Database State (inserts the full entrant + match tree in one call,
    # so it runs off the event loop)
    success, t_id, error_msg = await asyncio.to_thread(
        create_tournament, title, description, entrants, days_per_round
    )

    if not success:
        await interaction.followup.send(f"Database error while creating the tournament: {error_msg}")
        return

    # Generate the bracket image and post it to the #tournaments channel
    image_buffer = await generate_bracket_image(t_id)
    bracket_file = discord.File(fp=image_buffer, filename=f"bracket_{t_id}.png") if image_buffer else None
    msg = (
        f"🏆 **{title} has begun!** 🏆\n"
        f"{description}\n\n"
        "Round 1 voting polls will appear below shortly!"
    )

    if not bracket_file:
        msg += "\n\n*(The bracket image couldn't be generated this time.)*"
    await tournaments_channel.send(content=msg, file=bracket_file)

    # Post the polls for Round 1
    await post_round_polls(tournaments_channel, t_id, round_num=1, days_per_round=days_per_round)

    await interaction.followup.send(
        f"Successfully created tournament `{t_id}`, posted the bracket, and "
        f"launched Round 1 polls in {tournaments_channel.mention}!")

@discord.app_commands.command(name="force-close-round",
                              description="[Admin] Immediately end the active voting round for a tournament.")
@discord.app_commands.default_permissions(administrator=True) # Locks this to server admins
async def force_close_round(interaction: discord.Interaction, tournament_id: str):
    """Fast-forwards the clock on active polls so the background task resolves them."""
    await interaction.response.defer(ephemeral=True)
    affected_matches = force_close_active_round(tournament_id)
    if affected_matches > 0:
        await interaction.followup.send(
            f"⏩ **Fast-forwarded {affected_matches} matches!**\n"
            "The `tournament_resolution_loop` will tally the votes, "
            "advance the winners, and post the next round on its next background tick (within 5 minutes)."
        )
    else:
        await interaction.followup.send(
            "⚠️ **No active polls found.**\n"
            f"There are no unresolved polls currently running for tournament `{tournament_id}`."
        )
