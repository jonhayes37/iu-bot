"""Business logic for list event admin commands."""

import io
import logging
import re
import discord
from db.lists import create_new_event, close_event, get_all_submissions, get_event_details, set_event_message_id

logger = logging.getLogger('iu-bot')

@discord.app_commands.command(name='create-list-event', description="[Admin] Start a new list submission event.")
@discord.app_commands.default_permissions(administrator=True)
async def create_list_event(
    interaction: discord.Interaction,
    event_id: str,
    event_name: str,
    expected_count: int = 0,
    placeholder: str = "1. Berry Good // Don't Believe\n2. IVE // All Night (https://youtu.be/xU8mQMLx0tk?t=27)\n..."
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

@discord.app_commands.command(name='close-list-event',
                              description="[Admin] Close an active list event and disable its button.")
@discord.app_commands.default_permissions(administrator=True)
async def close_list_event(
    interaction: discord.Interaction,
    event_id: str
):
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

@discord.app_commands.command(name='export-lists',
              description="[Admin] Export all list submissions for a specific event to .csv and .txt files.")
@discord.app_commands.default_permissions(administrator=True)
async def export_lists(interaction: discord.Interaction, event_id: str):
    """Fetches data, formats it via the helper, and uploads the files to Discord."""
    await interaction.response.defer(ephemeral=True)

    event_details = get_event_details(event_id)
    if not event_details:
        await interaction.followup.send(f"Could not find event `{event_id}`.")
        return

    submissions = get_all_submissions(event_id)
    if not submissions:
        await interaction.followup.send(f"No submissions found for `{event_id}` yet!")
        return

    event_name = event_details.get('event_name', event_id)
    csv_string, txt_string = _process_export_data(event_name, submissions)

    csv_file = discord.File(
        fp=io.BytesIO(csv_string.encode('utf-8')),
        filename=f"{event_id}_stats.csv"
    )
    txt_file = discord.File(
        fp=io.BytesIO(txt_string.encode('utf-8')),
        filename=f"{event_id}_urls.txt"
    )

    await interaction.followup.send(
        content=f"Exported **{len(submissions)}** submissions for `{event_id}`!",
        files=[csv_file, txt_file]
    )

def _process_export_data(event_name: str, submissions: list[dict]) -> tuple[str, str]:
    """
    Transforms raw submission data into two TXT strings.
    Returns: (stats_string, editor_string)
    """
    stats_buffer = io.StringIO()
    editor_buffer = io.StringIO()

    editor_buffer.write(f"URL REFERENCE SHEET: {event_name}\n")
    editor_buffer.write("="*50 + "\n\n")

    for sub in submissions:
        username = sub.get('username', 'Unknown User')
        clean_text = sub.get('cleaned_text', '')
        urls_raw = sub.get('extracted_urls', '')

        stats_buffer.write(f"{username}\n{clean_text}\n")
        if urls_raw:
            urls = urls_raw.split(',')
            lines = clean_text.split('\n')

            if any(u.strip() for u in urls):
                editor_buffer.write(f"--- {username} ---\n")
                for i, url in enumerate(urls):
                    if url.strip():
                        pick_text = lines[i] if i < len(lines) else f"Pick #{i+1}"

                        # Extract the timestamp (matches ?t=58s, &t=1m2s, ?t=123, etc.)
                        time_match = re.search(r'[?&]t=([0-9hms]+)', url)
                        timestamp = f"(starts at {time_match.group(1)})" if time_match else ""
                        editor_buffer.write(f"{pick_text}\n-> {url}{timestamp}\n\n")

    return stats_buffer.getvalue(), editor_buffer.getvalue()
