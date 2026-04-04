"""Validation helpers"""

import discord

async def validate_channel(interaction: discord.Interaction, channel: str) -> bool:
    if interaction.channel.name != channel:
        await interaction.response.send_message(
            f"This command can only be used in the #{channel} channel.",
            ephemeral=True
        )
        return True

    return False
