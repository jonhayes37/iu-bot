"""Trigger logic for users typing in the roles channel"""

import logging

import discord
from db.roles import get_all_roles_grouped, get_display_message_ids, get_role_id, replace_display_message_ids


logger = logging.getLogger('iu-bot')

async def handle_role_assignment(message: discord.Message):
    """
    Handles parsing and assigning roles when a user types in the #roles channel.
    """
    # Delete the user's message to keep the channel clean.
    try:
        await message.delete()
    except discord.Forbidden:
        logger.error("Failed to delete message in #roles due to lack of permissions.")

    content = message.content.strip().lower()
    intent = ""
    intent, alias = _get_intent_from_message(content)
    if not intent:
        await message.channel.send("Invalid prefix! Must be either `add`, `+`, `remove`, or `-`.", delete_after=5.0)
        return

    role_id = get_role_id(alias)
    if not role_id:
        await message.channel.send(f"Could not find a role matching `{alias}`.", delete_after=5.0)
        return

    role = message.guild.get_role(role_id)
    if not role:
        await message.channel.send("Role exists in database but not in Discord! Ping <@904751089633615972>.",
                                   delete_after=5.0)
        return

    has_role = role in message.author.roles
    try:
        if intent == "add":
            if has_role:
                await message.channel.send(f"You already have the **{role.name}** role!", delete_after=5.0)
            else:
                await message.author.add_roles(role)
                await message.channel.send(f"Granted the **{role.name}** role!", delete_after=5.0)
        elif intent == "remove":
            if not has_role:
                await message.channel.send(f"You don't have the **{role.name}** role!", delete_after=5.0)
            else:
                await message.author.remove_roles(role)
                await message.channel.send(f"Removed the **{role.name}** role!", delete_after=5.0)

    except discord.Forbidden:
        await message.channel.send("I don't have permission to add that role!", delete_after=6.0)

def _get_intent_from_message(content: str) -> tuple[str, str]:
    add_prefixes = ("add ", "+")
    remove_prefixes = ("remove ", "-")

    if content.startswith(add_prefixes):
        intent = "add"
        for prefix in add_prefixes:
            if content.startswith(prefix):
                alias = content[len(prefix):].strip()
                return intent, alias
    elif content.startswith(remove_prefixes):
        intent = "remove"
        for prefix in remove_prefixes:
            if content.startswith(prefix):
                alias = content[len(prefix):].strip()
                return intent, alias
    return "", ""

def build_display_chunks() -> list[str]:
    """Builds the formatted strings, chunking them safely under 2000 characters."""
    grouped_data = get_all_roles_grouped()
    chunks = []
    current_chunk = ""

    for category, roles in grouped_data.items():
        cat_header = f"**{category}**\n"

        # Start a new chunk if the header pushes us over
        if len(current_chunk) + len(cat_header) > 1900:
            chunks.append(current_chunk.strip())
            current_chunk = ""

        current_chunk += cat_header

        for role_name, aliases in roles.items():
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

async def sync_roles_display(channel: discord.TextChannel):
    """Edits, adds, or deletes messages in the #roles channel to match the DB."""
    chunks = build_display_chunks()
    existing_ids = get_display_message_ids()
    new_tracked_ids = []

    for i, chunk in enumerate(chunks):
        if i < len(existing_ids):
            # We have an existing message to edit
            try:
                msg = await channel.fetch_message(existing_ids[i])
                await msg.edit(content=chunk)
                new_tracked_ids.append(msg.id)
            except discord.NotFound:
                # The message was manually deleted, so we create a new one
                new_msg = await channel.send(chunk)
                new_tracked_ids.append(new_msg.id)
        else:
            # We have more chunks than existing messages, so we send new ones
            new_msg = await channel.send(chunk)
            new_tracked_ids.append(new_msg.id)

    if len(existing_ids) > len(chunks):
        for leftover_id in existing_ids[len(chunks):]:
            try:
                msg = await channel.fetch_message(leftover_id)
                await msg.delete()
            except discord.NotFound:
                pass # Already deleted

    replace_display_message_ids(new_tracked_ids)
    logger.info("Successfully synced the #roles display messages.")
