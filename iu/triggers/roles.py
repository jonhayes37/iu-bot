"""Trigger logic for users typing in the roles channel"""

import logging
import sqlite3

import discord
from config import admin_user_id
from db.roles import get_role_id

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

    try:
        role_id = get_role_id(alias)
    except sqlite3.Error:
        logger.exception("Could not look up the role for '%s'.", alias)
        await message.channel.send("Something went wrong looking up that role. Please try again in a moment.",
                                   delete_after=5.0)
        return

    if not role_id:
        await message.channel.send(f"Could not find a role matching `{alias}`.", delete_after=5.0)
        return

    role = message.guild.get_role(role_id)
    if not role:
        await message.channel.send(f"Role exists in database but not in Discord! Ping <@{admin_user_id()}>.",
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
