"""UI elements for HMA Category Suggestions."""

import logging

import discord
from db.hmas import save_category_suggestion, get_user_category_suggestion

logger = logging.getLogger('iu-bot')

class HMACategorySuggestionModal(discord.ui.Modal):
    """Modal for suggesting updates to HMA categories."""

    def __init__(self, year: int, existing_data: dict = None):
        super().__init__(title=f'{year} HMA Category Suggestions')
        self.year = year

        def_new = existing_data['new_categories'] if existing_data else None
        def_drop = existing_data['dropped_categories'] if existing_data else None

        self.new_cats = discord.ui.TextInput(
            label='New categories to add',
            style=discord.TextStyle.paragraph,
            placeholder="e.g. Best Boy Group",
            default=def_new,
            required=False,
            max_length=1000
        )
        self.drop_cats = discord.ui.TextInput(
            label='Categories to remove',
            style=discord.TextStyle.paragraph,
            placeholder="e.g. Best Boy Group",
            default=def_drop,
            required=False,
            max_length=1000
        )

        self.add_item(self.new_cats)
        self.add_item(self.drop_cats)

    # pylint: disable=arguments-differ
    async def on_submit(self, interaction: discord.Interaction):
        val_new = self.new_cats.value.strip()
        val_drop = self.drop_cats.value.strip()

        if not val_new and not val_drop:
            await interaction.response.send_message(
                "❌ You left both fields blank! Please suggest at least one addition or removal.", 
                ephemeral=True
            )
            return

        try:
            save_category_suggestion(
                interaction.user.id,
                interaction.user.display_name,
                val_new,
                val_drop
            )
            await interaction.response.send_message(
                "✅ **Suggestions submitted!** These will be reviewed and voted on in polls soon.\n\n"
                "You can click the button again anytime before the polls are open to update your ideas.", 
                ephemeral=True
            )
        except Exception as e:
            logger.error("Error saving HMA suggestion: %s", e)
            await interaction.response.send_message("❌ Database error. Please ping an admin.", ephemeral=True)


class HMASuggestionsHub(discord.ui.View):
    """The persistent button for HMA suggestions."""
    def __init__(self, year: int):
        super().__init__(timeout=None)
        self.year = year

        for child in self.children:
            if getattr(child, "custom_id", None) == "btn_hma_suggest":
                child.custom_id = f"btn_hma_suggest_{self.year}"

    @discord.ui.button(label="Suggest Category Changes", style=discord.ButtonStyle.primary,
                       custom_id="btn_hma_suggest", emoji="💡")
    async def btn_suggest(self, interaction: discord.Interaction, _: discord.ui.Button):
        existing_data = get_user_category_suggestion(interaction.user.id)
        await interaction.response.send_modal(HMACategorySuggestionModal(self.year, existing_data))
