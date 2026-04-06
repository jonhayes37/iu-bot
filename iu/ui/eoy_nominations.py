"""UI elements for end of year nominations"""
import logging

import discord
from db.hof_nominations import save_hof_nomination, get_hof_nomination
from db.top_songs import save_top_songs, get_user_top_songs
from utils.validation import sanitize_list

logger = logging.getLogger('iu-bot')

class Top25Modal(discord.ui.Modal):
    """Modal for submitting top songs of the year and honourable mentions"""
    def __init__(self, year: int, existing_t25: str = None, existing_hms: str = None):
        # Set the modal title dynamically
        super().__init__(title=f'{year} End of Year: Top 25 Songs')
        self.year = year

        # Define TextInputs inside init so we can use the year variable
        self.top_25 = discord.ui.TextInput(
            label=f'Your {self.year} Top 25 Songs',
            style=discord.TextStyle.paragraph,
            placeholder="1. Berry Good // Don't Believe\n2. SNSD // Into the New World\n...",
            default=existing_t25,
            required=True,
            max_length=4000
        )
        self.hms = discord.ui.TextInput(
            label='3 Honourable Mentions',
            style=discord.TextStyle.paragraph,
            placeholder="1. IU // Blueming\n2. IVE // All Night\n...",
            default=existing_hms,
            required=True,
            max_length=1000
        )

        # Add the inputs to the modal
        self.add_item(self.top_25)
        self.add_item(self.hms)

    # pylint: disable=arguments-differ
    async def on_submit(self, interaction: discord.Interaction):
        raw_t25 = self.top_25.value
        raw_hms = self.hms.value

        # Run Validation
        is_valid_t25, err_t25, clean_t25, urls_t25 = sanitize_list(raw_t25, 25)
        is_valid_hms, err_hms, clean_hms, urls_hms = sanitize_list(raw_hms, 3)

        # Handle Failures gracefully so they don't lose their text
        if not is_valid_t25 or not is_valid_hms:
            error_details = []
            if not is_valid_t25:
                error_details.append(f"**Top 25:** {err_t25}")
            if not is_valid_hms:
                error_details.append(f"**Honourable Mentions:** {err_hms}")

            error_intro = (
                "❌ **Submission Failed** ❌\n"
                + "\n".join(error_details) + "\n\n"
                "Don't panic! Your lists are safe. Copy them from the messages below, "
                "fix the line counts, and try clicking the submit button again."
            )

            # Defer sending the long text to avoid Discord's 2000 character limit per message
            await interaction.response.send_message(error_intro, ephemeral=True)

            # Truncate slightly if they somehow maxed out the 4000 char limit to avoid a Discord API crash
            safe_t25 = raw_t25[:1900] + "..." if len(raw_t25) > 1900 else raw_t25
            await interaction.followup.send(f"**Your Top 25:**\n```{safe_t25}```", ephemeral=True)
            await interaction.followup.send(f"**Your HMs:**\n```{raw_hms}```", ephemeral=True)
            return

        # Save to Database
        try:
            user_id = interaction.user.id
            username = interaction.user.display_name

            save_top_songs(
                user_id, username,
                raw_t25, clean_t25, urls_t25,
                raw_hms, clean_hms, urls_hms
            )

            embed = discord.Embed(
                title=f"🎵 {self.year} Top 25 Submitted!",
                description=f"Your Top 25 Songs of **{self.year}** has been submitted! "
                    "Need to make a change? Just click the button again to edit your submission!",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error("Error saving Top 25 to the database: %s", e)
            await interaction.response.send_message("❌ Error saving to the database. Please ping an admin!",
                                                    ephemeral=True)

class HoFModal(discord.ui.Modal):
    """Modal for submitting Hall of Fame nominations"""
    def __init__(self, year: int, existing_text: str = None):
        super().__init__(title=f'{year} Hall of Fame Nominations')
        self.year = year

        self.hof_text = discord.ui.TextInput(
            label=f'Who should be inducted in {self.year}?',
            style=discord.TextStyle.paragraph,
            placeholder="BTS, Girls' Generation, Seventeen...",
            default=existing_text,
            required=True,
            max_length=4000
        )
        self.add_item(self.hof_text)

    # pylint: disable=arguments-differ
    async def on_submit(self, interaction: discord.Interaction):
        try:
            award_year = save_hof_nomination(
                interaction.user.id,
                interaction.user.display_name,
                self.hof_text.value
            )
            embed = discord.Embed(
                title="🏛️ HallyU Hall of Fame Nominations Submitted!",
                description=f"Your ballot for the **{award_year} Class** has been recorded.\n\n"
                            "Need to make a change? Just click the button again to edit your submission!",
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as ex:
            logger.error("Error saving to the database: %s", ex)
            await interaction.response.send_message("❌ Error saving to the database.", ephemeral=True)


class EOYNominationsHub(discord.ui.View):
    """Hub message with buttons for end of year nominations."""

    def __init__(self, year: int):
        super().__init__(timeout=None) # Persistent view
        self.year = year

        # Dynamically overwrite the button labels after they are created by the decorators
        for child in self.children:
            if getattr(child, "custom_id", None) == "btn_eoy_top25":
                child.label = f"Submit {self.year} Top 25 Songs"
            elif getattr(child, "custom_id", None) == "btn_eoy_hof":
                child.label = f"{self.year} HallyU Hall of Fame"

    @discord.ui.button(label="Top 25 Songs",
                       style=discord.ButtonStyle.primary,
                       custom_id="btn_eoy_top25",
                       emoji="🎵")
    async def btn_top_25(self, interaction: discord.Interaction, _: discord.ui.Button):
        existing_data = get_user_top_songs(interaction.user.id)
        t25_text = existing_data['top_25_raw'] if existing_data else None
        hms_text = existing_data['hms_raw'] if existing_data else None
        await interaction.response.send_modal(
            Top25Modal(year=self.year, existing_t25=t25_text, existing_hms=hms_text)
        )

    @discord.ui.button(label="HallyU Hall of Fame",
                       style=discord.ButtonStyle.success,
                       custom_id="btn_eoy_hof",
                       emoji="🏛️")
    async def btn_hof(self, interaction: discord.Interaction, _: discord.ui.Button):
        existing_text = get_hof_nomination(interaction.user.id)
        # Pass the year into the Modal
        await interaction.response.send_modal(HoFModal(year=self.year, existing_text=existing_text))
