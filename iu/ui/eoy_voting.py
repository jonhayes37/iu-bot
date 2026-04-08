"""UI elements for Phase 2: End of Year Voting."""
import logging

import discord
from db.hall_of_fame import get_official_hof_nominees, save_hof_vote, get_user_hof_vote
from db.hmas import (
    get_all_hma_categories, get_hma_final_nominees, save_hma_vote, get_user_hma_votes
)

logger = logging.getLogger('iu-bot')



class EOYVotingHub(discord.ui.View):
    """The persistent end of Year 2 Voting Hub."""
    def __init__(self, year: int):
        super().__init__(timeout=None)
        self.year = year

        # Dynamically inject the year
        for child in self.children:
            if getattr(child, "custom_id", None) == "btn_vote_hof":
                child.label = f"{self.year} HallyU Hall of Fame"
                child.custom_id = f"btn_vote_hof_{self.year}"
            if getattr(child, "custom_id", None) == "btn_vote_hma":
                child.label = f"{self.year} HallyU Music Awards"
                child.custom_id = f"btn_vote_hma_{self.year}"

    @discord.ui.button(label="Vote Hall of Fame", style=discord.ButtonStyle.success,
                       custom_id="btn_vote_hof", emoji="🏛️")
    async def btn_hof(self, interaction: discord.Interaction, _: discord.ui.Button):
        nominees = get_official_hof_nominees()

        if not nominees or len(nominees) < 3:
            await interaction.response.send_message(
                "❌ Voting hasn't started yet! The nominees are still being populated.", 
                ephemeral=True
            )
            return

        existing_vote = get_user_hof_vote(interaction.user.id)
        view = HoFVotingView(self.year, nominees, existing_vote)

        msg = f"**{self.year} HallyU Hall of Fame Ballot**\nSelect your top 3 choices below:"
        await interaction.response.send_message(content=msg, view=view, ephemeral=True)

    @discord.ui.button(label="Vote HMAs", style=discord.ButtonStyle.primary, custom_id="btn_vote_hma", emoji="🏆")
    async def btn_hma(self, interaction: discord.Interaction, _: discord.ui.Button):
        view = HMACategorySelectView(self.year, interaction.user.id)
        msg = "**HallyU Music Awards Ballot**\nCategories marked with ⏰ need your vote. ✅ are completed!"
        await interaction.response.send_message(content=msg, view=view, ephemeral=True)


class HoFVotingView(discord.ui.View):
    """The interactive ranked voting ballot for the Hall of Fame."""
    def __init__(self, year: int, nominees: list[str], existing_vote: dict = None):
        super().__init__(timeout=900) # 15 min timeout
        self.year = year

        # Determine defaults if they are editing a previous vote
        self.def1 = existing_vote['first_choice'] if existing_vote else None
        self.def2 = existing_vote['second_choice'] if existing_vote else None
        self.def3 = existing_vote['third_choice'] if existing_vote else None

        # Helper to build the options list and set the default selection
        def build_options(default_val):
            return [discord.SelectOption(label=name, value=name, default=name == default_val) for name in nominees]

        self.first_select = discord.ui.Select(
            placeholder="🥇 1st Choice (3 Points)",
            options=build_options(self.def1), row=0
        )
        self.second_select = discord.ui.Select(
            placeholder="🥈 2nd Choice (2 Points)",
            options=build_options(self.def2), row=1
        )
        self.third_select = discord.ui.Select(
            placeholder="🥉 3rd Choice (1 Point)",
            options=build_options(self.def3), row=2
        )

        # Silent acknowledgment callback to prevent Discord from timing out the interaction
        async def select_callback(interaction: discord.Interaction):
            await interaction.response.defer()

        self.first_select.callback = select_callback
        self.second_select.callback = select_callback
        self.third_select.callback = select_callback

        self.add_item(self.first_select)
        self.add_item(self.second_select)
        self.add_item(self.third_select)

    @discord.ui.button(label="Submit Ballot", style=discord.ButtonStyle.success, row=3)
    async def btn_submit(self, interaction: discord.Interaction, _: discord.ui.Button):
        v1 = self.first_select.values[0] if self.first_select.values else self.def1
        v2 = self.second_select.values[0] if self.second_select.values else self.def2
        v3 = self.third_select.values[0] if self.third_select.values else self.def3

        if not v1 or not v2 or not v3:
            await interaction.response.send_message(
                "❌ **Incomplete Ballot:** You must select a 1st, 2nd, and 3rd choice.", 
                ephemeral=True
            )
            return

        # Prevent duplicate selections
        if len(set([v1, v2, v3])) < 3:
            await interaction.response.send_message(
                "❌ **Invalid Ballot:** You cannot vote for the same nominee more than once! "
                "Please adjust your choices above and try again.", 
                ephemeral=True
            )
            return

        # Save to database
        try:
            save_hof_vote(interaction.user.id, v1, v2, v3)
            embed = discord.Embed(
                title=f"🏛️ {self.year} Hall of Fame Ballot Secured!",
                description="Your ranked votes have been successfully recorded.",
                color=discord.Color.gold()
            )
            embed.add_field(name="🥇 1st Choice", value=v1, inline=False)
            embed.add_field(name="🥈 2nd Choice", value=v2, inline=False)
            embed.add_field(name="🥉 3rd Choice", value=v3, inline=False)

            await interaction.response.edit_message(embed=embed, view=None)

        except Exception as e:
            logger.error("Database error saving HoF vote: %s", e)
            await interaction.response.send_message("❌ Database error. Please ping an admin.", ephemeral=True)


class HMABallotView(discord.ui.View):
    """The interactive ranked ballot for a single HMA category."""
    def __init__(self, year: int, user_id: int, category_id: str, category_name: str,
                 nominees: list[str], existing_vote: dict = None):
        super().__init__(timeout=900)
        self.year = year
        self.user_id = user_id
        self.category_id = category_id
        self.category_name = category_name

        self.def1 = existing_vote['first_choice'] if existing_vote else None
        self.def2 = existing_vote['second_choice'] if existing_vote else None
        self.def3 = existing_vote['third_choice'] if existing_vote else None

        def build_options(default_val):
            return [discord.SelectOption(label=name, value=name, default=name == default_val) for name in nominees]

        self.first_select = discord.ui.Select(placeholder="🥇 1st Choice (3 Points)",
                                              options=build_options(self.def1), row=0)
        self.second_select = discord.ui.Select(placeholder="🥈 2nd Choice (2 Points)",
                                               options=build_options(self.def2), row=1)
        self.third_select = discord.ui.Select(placeholder="🥉 3rd Choice (1 Point)",
                                              options=build_options(self.def3), row=2)

        async def select_callback(interaction: discord.Interaction):
            await interaction.response.defer()

        self.first_select.callback = select_callback
        self.second_select.callback = select_callback
        self.third_select.callback = select_callback

        self.add_item(self.first_select)
        self.add_item(self.second_select)
        self.add_item(self.third_select)

    @discord.ui.button(label="Save Vote", style=discord.ButtonStyle.success, row=3)
    async def btn_save(self, interaction: discord.Interaction, _: discord.ui.Button):
        v1 = self.first_select.values[0] if self.first_select.values else self.def1
        v2 = self.second_select.values[0] if self.second_select.values else self.def2
        v3 = self.third_select.values[0] if self.third_select.values else self.def3

        if not v1 or not v2 or not v3:
            await interaction.response.send_message("❌ **Incomplete:** Select a 1st, 2nd, and 3rd choice.",
                                                    ephemeral=True)
            return

        if len(set([v1, v2, v3])) < 3:
            await interaction.response.send_message(
                "❌ **Duplicate:** You cannot vote for the same nominee more than once.",
                ephemeral=True)
            return

        try:
            # Save the vote and immediately return them to the category selector!
            save_hma_vote(interaction.user.id, self.category_id, v1, v2, v3)
            view = HMACategorySelectView(self.year, self.user_id)
            msg = f"✅ Saved vote for **{self.category_name}**!\n\n**HallyU Music Awards Ballot**\n" \
                "Select your next category:"
            await interaction.response.edit_message(content=msg, view=view)
        except Exception as e:
            logger.error("Error saving HMA vote: %s", e)
            await interaction.response.send_message("❌ Database error.", ephemeral=True)

    @discord.ui.button(label="Back to Categories", style=discord.ButtonStyle.secondary, row=3)
    async def btn_back(self, interaction: discord.Interaction, _: discord.ui.Button):
        # Allow them to back out without saving
        view = HMACategorySelectView(self.year, self.user_id)
        msg = "**HallyU Music Awards Ballot**\nCategories marked with ⏰ need your vote. ✅ are completed!"
        await interaction.response.edit_message(content=msg, view=view)


class HMACategoryDropdown(discord.ui.Select):
    """A single dynamic dropdown that holds up to 25 categories."""
    def __init__(self, options: list[discord.SelectOption], year: int, user_id: int):
        super().__init__(placeholder="Select a category to vote...", options=options)
        self.year = year
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        category_id = self.values[0]
        category_name = next(opt.label for opt in self.options if opt.value == category_id)

        nominees = get_hma_final_nominees(category_id)
        if not nominees or len(nominees) < 3:
            await interaction.response.send_message(
                f"❌ Final nominees for **{category_name}** are not available yet!",
                ephemeral=True
            )
            return

        user_votes = get_user_hma_votes(self.user_id)
        existing_vote = user_votes.get(category_id)

        # Transition to the actual voting ballot for this category
        view = HMABallotView(self.year, self.user_id, category_id, category_name, nominees, existing_vote)
        await interaction.response.edit_message(content=f"**{category_name}**\nSelect your top 3 choices:", view=view)


class HMACategorySelectView(discord.ui.View):
    """The dynamic router view that sorts ⏰ and ✅ categories and handles pagination."""
    def __init__(self, year: int, user_id: int):
        super().__init__(timeout=900)
        self.year = year
        self.user_id = user_id

        categories = get_all_hma_categories()
        user_votes = get_user_hma_votes(user_id)

        unvoted_opts = []
        voted_opts = []

        for cat in categories:
            label = cat['name'][:95] # Safety truncation for Discord UI limits
            cat_id = cat['category_id']
            if cat_id in user_votes:
                voted_opts.append(discord.SelectOption(label=label, value=cat_id, emoji="✅"))
            else:
                unvoted_opts.append(discord.SelectOption(label=label, value=cat_id, emoji="⏰"))

        all_options = unvoted_opts + voted_opts

        # Chunk the options into groups of 25 to bypass Discord's hard limit
        chunks = [all_options[i:i + 25] for i in range(0, len(all_options), 25)]

        for chunk in chunks:
            self.add_item(HMACategoryDropdown(chunk, self.year, self.user_id))
