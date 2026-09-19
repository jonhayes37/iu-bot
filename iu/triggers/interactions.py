"""Routes button clicks that aren't handled by a registered persistent view."""

import discord

from ui.lists import handle_list_button_click


async def handle_interaction(interaction: discord.Interaction):
    """Handles the dynamic list submission buttons (custom ids look like submit_list:<event_id>)."""
    # We only care about button clicks (Components)
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get('custom_id', '')
    if not custom_id.startswith('submit_list:'):
        return

    # If the event is closed, the ID looks like submit_list:mid_2026_closed
    if custom_id.endswith('_closed'):
        await interaction.response.send_message("Submissions for this event are closed!", ephemeral=True)
        return

    # Extract the event_id (e.g., "mid_2026")
    event_id = custom_id.split(':')[1]
    await handle_list_button_click(interaction, event_id)
