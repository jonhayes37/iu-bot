"""Business logic for role-related commands."""

import logging
import discord
from db.roles import register_new_role

from triggers.roles import sync_roles_display

logger = logging.getLogger('iu-bot')

async def handle_register_role(
    interaction: discord.Interaction,
    role: discord.Role,
    category: str,
    aliases: str
):
    """Parses input, updates the database, and syncs the #roles channel UI."""
    # Defer the response since syncing the channel might take a second
    await interaction.response.defer(ephemeral=True)

    alias_list = [a.strip() for a in aliases.split(',')] if aliases else []
    success = register_new_role(role.id, role.name, category, alias_list)
    if not success:
        await interaction.followup.send(f"Database error: Failed to register **{role.name}**.")
        return

    # Trigger a UI sync
    roles_channel = discord.utils.get(interaction.guild.text_channels, name='roles')
    if roles_channel:
        await sync_roles_display(roles_channel)
        await interaction.followup.send(
            f"Registered **{role.name}** under **{category}** and updated the channel!", ephemeral=True)
    else:
        await interaction.followup.send(
            f"Registered **{role.name}**, but I couldn't find the `#roles` channel to update the display.",
            ephemeral=True)
        logger.error("Roles channel not found during sync attempt.")
