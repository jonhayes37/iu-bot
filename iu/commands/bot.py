"""Bot management commands"""
import typing

import discord

@discord.app_commands.command(name='set-status',
              description="[Admin] Change IU's status message for a specific user's perk.")
@discord.app_commands.describe(
    member="The user who purchased the status perk",
    status_text="The text to display after 'Listening to'"
)
@discord.app_commands.default_permissions(administrator=True)
async def set_iu_status(interaction: discord.Interaction, member: discord.Member, status_text: typing.Optional[str]):
    """Changes the bot's status and logs the user who requested it."""

    if interaction.channel.name != 'dispatch-news':
        await interaction.response.send_message(
            "This command can only be used in the #dispatch-news channel.", 
            ephemeral=True
        )
        return

    # Update the bot's presence
    if status_text == "":
        await interaction.client.change_presence(status=discord.Status.online, activity=None)
    else:
        activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
        await interaction.client.change_presence(status=discord.Status.online, activity=activity)

    # Log the change with the member tagged!
    await interaction.response.send_message(
        f"<@1132749272488624189>'s status has been updated by {member.mention} to `{status_text}`"
    )
