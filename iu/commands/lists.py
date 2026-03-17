"""Business logic for list event admin commands."""

import logging
import discord
from db.lists import create_new_event, close_event, get_event_details, set_event_message_id

logger = logging.getLogger('iu-bot')

async def handle_create_list_event(
    interaction: discord.Interaction,
    event_id: str,
    event_name: str,
    expected_count: int,
    placeholder: str
):
    """Creates the event in the DB and posts a clean button."""
    await interaction.response.defer(ephemeral=True)

    success = create_new_event(event_id, event_name, expected_count, placeholder)
    if not success:
        await interaction.followup.send(f"Failed to create event. Does the ID `{event_id}` already exist?")
        return

    # Build the Button
    view = discord.ui.View(timeout=None)
    button = discord.ui.Button(
        label="Submit Your List",
        style=discord.ButtonStyle.primary,
        custom_id=f"submit_list:{event_id}",
        emoji="📥"
    )
    view.add_item(button)

    # Post it to the channel with a minimal anchor text
    msg_content = f"**{event_name}**\nClick below to submit your list!"
    announcement_msg = await interaction.channel.send(content=msg_content, view=view)
    set_event_message_id(event_id, str(announcement_msg.id))

    await interaction.delete_original_response()

async def handle_close_list_event(interaction: discord.Interaction, event_id: str):
    await interaction.response.defer(ephemeral=True)

    # Look up the event to get the saved message_id
    event_details = get_event_details(event_id)
    if not event_details:
        await interaction.followup.send(f"Could not find event `{event_id}` in the database.", ephemeral=True)
        return

    message_id = event_details.get("message_id")
    if not message_id:
        await interaction.followup.send(f"Event `{event_id}` exists, but it has no message ID to update.",
                                        ephemeral=True)
        return

    # Update the Database
    success = close_event(event_id)
    if not success:
        await interaction.followup.send("Failed to close event in the database.", ephemeral=True)
        return

    # Find the announcement message and edit the button
    try:
        message = await interaction.channel.fetch_message(int(message_id))
        view = discord.ui.View(timeout=None)
        button = discord.ui.Button(
            label="Submissions Closed",
            style=discord.ButtonStyle.secondary,
            custom_id=f"submit_list:{event_id}_closed",
            disabled=True,
            emoji="🔒"
        )
        view.add_item(button)

        await message.edit(view=view)
        await interaction.followup.send(f"Event `{event_id}` closed!", ephemeral=True)

    except discord.NotFound:
        await interaction.followup.send("Event closed in DB, but the original message was deleted from the channel.",
                                        ephemeral=True)
    except Exception as ex:
        logger.error("Error updating message for closed event %s: %s", event_id, ex)
        await interaction.followup.send("Event closed, but failed to edit the message.", ephemeral=True)
