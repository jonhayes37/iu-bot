"""Button for toggling the Watch Parties role"""

import discord

WATCH_PARTIES_ROLE_ID = 1007397379462418463

class WatchPartyRoleView(discord.ui.View):
    """A persistent view that allows users to toggle the Watch Parties role on and off."""

    def __init__(self):
        # timeout=None is required so the button doesn't die after 15 minutes
        super().__init__(timeout=None)

    # The custom_id is how Discord remembers this exact button across bot restarts
    @discord.ui.button(
        label="Toggle Watch Parties Role",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_watch_parties_button"
    )
    async def toggle_role(self, interaction: discord.Interaction, _: discord.ui.Button):
        role = interaction.guild.get_role(WATCH_PARTIES_ROLE_ID)
        if not role:
            return await interaction.response.send_message("Error: Role not found.", ephemeral=True)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Removed the **{role.name}** role!", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"Added the **{role.name}** role! You'll be pinged when a new event is made.", ephemeral=True)
