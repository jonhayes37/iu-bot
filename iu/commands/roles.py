"""Business logic for role-related commands."""

import logging
import discord
from db.roles import (
    get_all_roles_grouped, get_display_message_ids, register_new_role,
    replace_display_message_ids
)

logger = logging.getLogger('iu-bot')

@discord.app_commands.command(name='register-role',
                              description="[Admin] Add a new assignable role to the #roles channel.")
@discord.app_commands.default_permissions(administrator=True)
async def register_role(
    interaction: discord.Interaction,
    role: discord.Role,
    category: str,
    aliases: str = ""  # Making it optional in the Discord UI
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
        await _sync_roles_display(roles_channel)
        await interaction.followup.send(
            f"Registered **{role.name}** under **{category}** and updated the channel!", ephemeral=True)
    else:
        await interaction.followup.send(
            f"Registered **{role.name}**, but I couldn't find the `#roles` channel to update the display.",
            ephemeral=True)
        logger.error("Roles channel not found during sync attempt.")

@discord.app_commands.command(name='sync-roles', description="[Admin] Sync the roles display in the #roles channel.")
@discord.app_commands.default_permissions(administrator=True)
async def sync_roles(
    interaction: discord.Interaction
):
    """Edits, adds, or deletes messages in the #roles channel to match the DB."""
    roles_channel = discord.utils.get(interaction.guild.text_channels, name='roles')
    if not roles_channel:
        return

    await _sync_roles_display(roles_channel)

async def _sync_roles_display(roles_channel: discord.TextChannel):
    chunks = _build_display_chunks()
    existing_ids = get_display_message_ids()
    new_tracked_ids = []

    for i, chunk in enumerate(chunks):
        if i < len(existing_ids):
            # We have an existing message to edit
            try:
                msg = await roles_channel.fetch_message(existing_ids[i])
                await msg.edit(content=chunk)
                new_tracked_ids.append(msg.id)
            except discord.NotFound:
                # The message was manually deleted, so we create a new one
                new_msg = await roles_channel.send(chunk)
                new_tracked_ids.append(new_msg.id)
        else:
            # We have more chunks than existing messages, so we send new ones
            new_msg = await roles_channel.send(chunk)
            new_tracked_ids.append(new_msg.id)

    if len(existing_ids) > len(chunks):
        for leftover_id in existing_ids[len(chunks):]:
            try:
                msg = await roles_channel.fetch_message(leftover_id)
                await msg.delete()
            except discord.NotFound:
                pass # Already deleted

    replace_display_message_ids(new_tracked_ids)
    logger.info("Successfully synced the #roles display messages.")

def _build_display_chunks() -> list[str]:
    """Builds the formatted strings, chunking them safely under 2000 characters."""
    grouped_data = get_all_roles_grouped()
    chunks = []
    current_chunk = ""

    # Sort categories case-insensitively
    for category in sorted(grouped_data.keys(), key=str.casefold):
        roles = grouped_data[category]
        cat_header = f"**{category}**\n"

        # Start a new chunk if the header pushes us over
        if len(current_chunk) + len(cat_header) > 1900:
            chunks.append(current_chunk.strip())
            current_chunk = ""

        current_chunk += cat_header

        # Sort role names case-insensitively
        for role_name, aliases in sorted(roles.items(), key=lambda item: item[0].casefold()):
            line = f"- `{role_name}`"
            if aliases:
                alias_str = ", ".join(f"`{a}`" for a in aliases)
                line += f" (aliases {alias_str})"
            line += "\n"

            # Start a new chunk if this specific role pushes us over
            if len(current_chunk) + len(line) > 1900:
                chunks.append(current_chunk.strip())
                current_chunk = line
            else:
                current_chunk += line

        current_chunk += "\n" # Spacing between categories

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks
