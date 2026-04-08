"""UI view for HMA nominations"""

import discord
from db.hmas import add_nomination, get_family_choices
from services.youtube import contains_youtube_url

class MultiNominationView(discord.ui.View):
    """View for multi-select for nominations"""

    def __init__(self, nominee: str):
        super().__init__(timeout=900) # 15 minute timeout
        self.nominee = nominee

        # Build options for Daesangs
        daesang_opts = [
            discord.SelectOption(label=name, value=cat_id)
            for cat_id, name in get_family_choices('daesang')[:25]
        ]
        self.daesang_select = discord.ui.Select(
            placeholder="Select Daesangs...",
            min_values=0, max_values=len(daesang_opts),
            options=daesang_opts, row=0
        )

        # Build options for Bonsangs
        bonsang_opts = [
            discord.SelectOption(label=name, value=cat_id)
            for cat_id, name in get_family_choices('bonsang')[:25]
        ]
        self.bonsang_select = discord.ui.Select(
            placeholder="Select Bonsangs...",
            min_values=0, max_values=len(bonsang_opts),
            options=bonsang_opts, row=1
        )

        # Build options for Fun
        fun_opts = [
            discord.SelectOption(label=name, value=cat_id)
            for cat_id, name in get_family_choices('fun')[:25]
        ]
        self.fun_select = discord.ui.Select(
            placeholder="Select Fun Awards...",
            min_values=0, max_values=len(fun_opts),
            options=fun_opts, row=2
        )

        # Ignore selections until the submit button is pressed
        async def select_callback(interaction: discord.Interaction):
            await interaction.response.defer()

        self.daesang_select.callback = select_callback
        self.bonsang_select.callback = select_callback
        self.fun_select.callback = select_callback

        # Add the dropdowns to the view
        self.add_item(self.daesang_select)
        self.add_item(self.bonsang_select)
        self.add_item(self.fun_select)

    @discord.ui.button(label="Submit Nominations", style=discord.ButtonStyle.success, row=3)
    async def submit_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        selected_ids = []
        selected_names = []

        # Create a lookup dictionary to grab the display names for the final embed
        id_to_name = {
            opt.value: opt.label
            for opt in self.daesang_select.options + self.bonsang_select.options + self.fun_select.options
        }

        # Gather all selections across all 3 dropdowns
        for select in (self.daesang_select, self.bonsang_select, self.fun_select):
            for val in select.values:
                selected_ids.append(val)
                selected_names.append(id_to_name[val])

        # Check at least something is selected
        if not selected_ids:
            await interaction.response.send_message(
                "❌ You must select at least one category!", 
                ephemeral=True
            )
            return

        # URL check for covers
        if 'best_dance_cover' in selected_ids or 'best_vocal_cover' in selected_ids:
            if not contains_youtube_url(self.nominee):
                await interaction.response.send_message(
                    "❌ Nominations for Best Dance/Vocal Cover must include a "
                    "valid YouTube URL in the nominee text!",
                    ephemeral=True
                )
                return

        # Process the nominations
        try:
            award_year = None
            for cat_id in selected_ids:
                award_year = add_nomination(interaction.user.id, cat_id, self.nominee)
        except Exception as ex:
            await interaction.response.send_message(f"❌ Database error: {ex}", ephemeral=True)
            return

        # Format the confirmation message
        formatted_categories = "\n".join([f"• {name}" for name in selected_names])

        embed = discord.Embed(
            title="🏆 Nominations Submitted!",
            description=f"Your ballots for the **{award_year} HallyU Music Awards** have been securely recorded.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Nominee", value=f"**{self.nominee}**", inline=False)
        embed.add_field(name="Categories", value=formatted_categories, inline=False)

        # Replace the dropdowns with the success embed
        await interaction.response.edit_message(content=None, embed=embed, view=None)
