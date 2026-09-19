"""UI elements for the listen game"""
import logging
from dataclasses import dataclass

import discord
from discord.ui import Select, TextInput, Button
from ui.base import SafeModal, SafeView
from config import Role
from db.listen_game import (
    Game, GameStatus, RankingPick, RoundResult, SaveResult, Submission, clear_ranking_picks_db,
    get_game_by_status_db, get_registered_players_db, register_player_db, save_ranking_pick_db,
    save_round_results_db, set_round_theme_db, unregister_player_db, update_round_ruleset_message_db,
    update_round_status_message_db
)
from services.listen_game_reveal import start_reveal
from utils.strings import get_ordinal

logger = logging.getLogger('iu-bot')

class JoinGameView(SafeView):
    """UI view for the join game button"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, custom_id="leave_listen_game")
    async def leave_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        game = get_game_by_status_db(GameStatus.REGISTRATION)
        if not game:
            await interaction.response.send_message("⚠️ No registration session is active.", ephemeral=True)
            return

        success = unregister_player_db(game.game_id, interaction.user.id)
        if not success:
            await interaction.response.send_message("You aren't registered for this game.", ephemeral=True)
            return

        # Re-fetch state and instantly overwrite the embed message layout
        await self._refresh_roster_embed(interaction, game)

    @discord.ui.button(label="Join Listen Game!", style=discord.ButtonStyle.primary, custom_id="join_listen_game")
    async def join_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        game = get_game_by_status_db(GameStatus.REGISTRATION)
        if not game:
            await interaction.response.send_message("⚠️ No registration session is active.", ephemeral=True)
            return

        success = register_player_db(game.game_id, interaction.user.id)
        if not success:
            await interaction.response.send_message("You are already registered!", ephemeral=True)
            return

        # Handle backend role assignment
        if interaction.guild and isinstance(interaction.user, discord.Member):
            target_role = discord.utils.get(interaction.guild.roles, name=Role.LISTEN_GAME_PLAYER)
            if target_role and target_role not in interaction.user.roles:
                try:
                    await interaction.user.add_roles(target_role)
                except discord.Forbidden:
                    logger.error("Error: Bot lacks permission to assign the role.")
                except discord.HTTPException as ex:
                    logger.error("HTTPException while assigning role: %s", ex)

        # Re-fetch state and overwrite the embed message layout
        await self._refresh_roster_embed(interaction, game)

    async def _refresh_roster_embed(self, interaction: discord.Interaction, game: Game):
        """Helper function to recalculate the roster and update the embed."""
        players = get_registered_players_db(game.game_id)
        max_round_days = game.max_round_days
        deadline_text = f"**Max Round Duration:** {max_round_days} Days" if max_round_days \
            else "**Max Round Duration:** None (GM Managed)"

        # Rebuild the base embed layout
        gm_mention = f"<@{game.gm_id}>"
        embed = discord.Embed(
            title="🎵 A New Listen Game is Starting!",
            description=f"{gm_mention} has opened registration for a new game.\n\n{deadline_text}\n\n"
                        "Click the buttons below to secure your spot!",
            color=0x9b59b6
        )

        if players:
            player_mentions = []
            for uid in players:
                member = interaction.guild.get_member(uid)
                if member:
                    player_mentions.append(f"• {member.mention}")
                else:
                    player_mentions.append(f"• <@{uid}>")

            # Display a clean text list of every player currently signed up, one per line
            embed.add_field(
                name=f"👥 {len(players)} Registered Players",
                value="\n".join(player_mentions),
                inline=False
            )
        else:
            embed.add_field(
                name="👥 Registered Players (0)",
                value="No one has joined yet. Be the first!",
                inline=False
            )

        # Edit the parent message directly
        await interaction.response.edit_message(embed=embed, view=self)

class SetThemeModal(SafeModal, title='Set Listen Game Ruleset'):
    """Modal for submitting or updating a theme for a listen game round"""

    theme_text = discord.ui.TextInput(
        label='Round Ruleset',
        style=discord.TextStyle.paragraph,
        placeholder='Share the ruleset for your round!',
        required=True,
        max_length=3500 # Plenty of space for paragraphs of rules
    )

    def __init__(self, game_id: int, round_id: int, existing_theme: str = None, ruleset_msg_id: int = None):
        super().__init__()
        self.game_id = game_id
        self.round_id = round_id
        self.ruleset_msg_id = ruleset_msg_id

        # Pre-populate the text box if an existing ruleset was passed in
        if existing_theme:
            self.theme_text.default = existing_theme

    # pylint: disable=arguments-differ
    async def on_submit(self, interaction: discord.Interaction):
        if not set_round_theme_db(self.round_id, self.theme_text.value):
            await interaction.response.send_message(
                "⚠️ This round is no longer accepting a ruleset, so nothing was changed.", ephemeral=True)
            return

        # Build the broadcast embed
        embed = discord.Embed(
            title="🎧 New Listen Game Round Started!",
            description=self.theme_text.value,
            color=0x3498db
        )

        # Display the host's avatar and name
        avatar_url = interaction.user.display_avatar.url if interaction.user.display_avatar else None
        embed.set_author(name=f"Listener: {interaction.user.display_name}", icon_url=avatar_url)
        embed.set_footer(text="Use `/listen-game-submit-song` to submit your track!")

        # Listen Game Player role is hardcoded here
        target_role = discord.utils.get(interaction.guild.roles, name=Role.LISTEN_GAME_PLAYER)
        role_mention = target_role.mention if target_role else ""

        if self.ruleset_msg_id:
            try:
                # Fetch and edit the original message
                ruleset_msg = await interaction.channel.fetch_message(self.ruleset_msg_id)
                await ruleset_msg.edit(embed=embed)

                # Publicly announce the update
                await interaction.response.send_message(
                    f"📢 {role_mention} **The ruleset has been updated by {interaction.user.mention}!**",
                    allowed_mentions=discord.AllowedMentions(roles=True)
                )
            except discord.NotFound:
                await interaction.response.send_message(
                    "⚠️ The ruleset was saved, but the original message was deleted so it couldn't be updated", 
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                content=f"{role_mention} The new ruleset has been posted. It's time to submit your songs!",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True)
            )

            try:
                ruleset_msg = await interaction.original_response()
                update_round_ruleset_message_db(self.round_id, ruleset_msg.id)
            except discord.HTTPException as e:
                logger.warning("Failed to fetch and save ruleset message ID: %s", e)

            players = get_registered_players_db(self.game_id)
            total_needed = len(players) - 1

            # Post the initial tracker message
            tracker_msg = await interaction.channel.send(
                f"🎧 **Round Status:** We are at `0/{total_needed}` submissions for the round."
            )

            # Save it to the DB
            update_round_status_message_db(self.round_id, tracker_msg.id)


@dataclass
class RankedSong:
    """A song the listener has ranked, with their commentary."""
    submission: Submission
    rank: int
    commentary: str


class CommentaryModal(SafeModal):
    """UI modal for letting the play add commentary for a ranking"""

    def __init__(self, view_instance: "ListenGameRankingView", selected_song: Submission, current_rank: int):
        super().__init__(title=f"{get_ordinal(current_rank)} Place Commentary")
        self.view_instance = view_instance
        self.selected_song = selected_song

        self.commentary = TextInput(
            label=f"For {selected_song.raw_title[:37]}",
            style=discord.TextStyle.paragraph,
            placeholder="Share your thoughts here!",
            required=True,
            max_length=1000
        )
        self.add_item(self.commentary)

    # pylint: disable=arguments-differ
    async def on_submit(self, interaction: discord.Interaction):
        await self.view_instance.rank_song(interaction, self.selected_song, self.commentary.value)


class RankingSelect(Select):
    """UI for the selector to choose songs to rank"""

    def __init__(self, unranked_submissions: list[Submission], current_rank: int):
        options = []
        for sub in unranked_submissions:
            options.append(discord.SelectOption(
                label=sub.raw_title[:100],
                value=sub.video_id
            ))

        super().__init__(
            placeholder=f"Select your pick for Rank #{current_rank}...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_video_id = self.values[0]
        selected_song = next(s for s in self.view.unranked_submissions if s.video_id == selected_video_id)

        # Launch the modal to get their commentary
        modal = CommentaryModal(self.view, selected_song, self.view.current_rank)
        await interaction.response.send_modal(modal)


class ConfirmRankingButton(Button):
    """Button to finalize rankings, save to DB, and trigger the channel reveal."""

    def __init__(self, game_id: int, round_id: int, listen_channel_id: int):
        super().__init__(label="Confirm & Publish Results", style=discord.ButtonStyle.success, emoji="✅")
        self.game_id = game_id
        self.round_id = round_id
        self.listen_channel_id = listen_channel_id

    async def callback(self, interaction: discord.Interaction):
        # Cheap guard against a double-click on this view. The real protection is in the database:
        # save_round_results_db only accepts a round that is still in the 'ranking' status.
        if self.view.results_confirmed:
            await interaction.response.send_message(
                "Results are already being published for this round.", ephemeral=True
            )
            return
        self.view.results_confirmed = True

        await interaction.response.defer()

        total_submissions = len(self.view.ranked_submissions)
        results_to_save = [
            RoundResult(
                user_id=item.submission.user_id,
                rank=item.rank,
                points=total_submissions - item.rank + 1,
                commentary=item.commentary
            )
            for item in self.view.ranked_submissions
        ]

        try:
            outcome = save_round_results_db(self.game_id, self.round_id, results_to_save)
        except Exception:
            self.view.results_confirmed = False  # allow a retry since nothing was actually saved
            raise

        if outcome is SaveResult.SAVED:
            await interaction.followup.send("✅ Results locked in! The reveal is starting in the game channel.",
                                            ephemeral=True)
        else:
            await interaction.followup.send(
                "ℹ️ The results for this round were already saved, so nothing was changed. "
                "Making sure the reveal is running.", ephemeral=True)

        # The reveal is resumable, so if the channel can't be found now the hourly listen game
        # check will start it.
        channel = interaction.client.get_channel(self.listen_channel_id)
        if channel:
            start_reveal(channel, self.round_id)
        else:
            logger.warning("Could not find channel %s to reveal round %s.", self.listen_channel_id, self.round_id)


class StartOverButton(Button):
    """Throws away the rankings made so far, so the listener can begin again."""

    def __init__(self):
        super().__init__(label="Start over", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)

    async def callback(self, interaction: discord.Interaction):
        await self.view.start_over(interaction)


class ListenGameRankingView(SafeView):
    """
    Interactive view managing the draft-style ranking process. Each pick is saved as it is made, so
    if the bot restarts or the message is dismissed, running the command again carries on from there.
    """

    def __init__(self, submissions: list[Submission], saved_picks: list[RankingPick],
                 game_id: int, round_id: int, listen_channel_id: int):
        super().__init__(timeout=None)
        self.all_submissions = submissions
        self.unranked_submissions = list(submissions)
        self.ranked_submissions: list[RankedSong] = []
        self.current_rank = len(submissions)

        # Store the IDs in the View
        self.game_id = game_id
        self.round_id = round_id
        self.listen_channel_id = listen_channel_id
        self.results_confirmed = False

        self._restore(saved_picks)
        self.setup_select_menu()

    def _restore(self, saved_picks: list[RankingPick]):
        """Puts back the picks saved by an earlier session (for songs that are still in the round)."""
        by_user = {sub.user_id: sub for sub in self.unranked_submissions}
        for pick in saved_picks:
            submission = by_user.pop(pick.user_id, None)
            if submission:
                self.ranked_submissions.append(RankedSong(submission, pick.rank, pick.commentary))
        self.unranked_submissions = [sub for sub in self.unranked_submissions if sub.user_id in by_user]
        self.current_rank = len(self.all_submissions) - len(self.ranked_submissions)

    def setup_select_menu(self):
        """Shows the control that fits how far along the listener is."""
        self.clear_items()

        # If there are multiple items, use the standard Select menu
        if len(self.unranked_submissions) > 1:
            self.add_item(RankingSelect(self.unranked_submissions, self.current_rank))
        # If there is one item left, use a button to prevent being stuck on dismissed modal
        elif len(self.unranked_submissions) == 1:
            self.add_item(RankSingleSongButton(self.unranked_submissions[0], self.current_rank))
        # If the list is empty, show the Confirm button
        else:
            self.add_item(ConfirmRankingButton(self.game_id, self.round_id, self.listen_channel_id))

        if self.ranked_submissions:
            self.add_item(StartOverButton())

    def build_embed(self) -> discord.Embed:
        """The message shown above the controls."""
        if not self.ranked_submissions:
            return discord.Embed(
                title="Listen Game Rankings",
                description="Select the song you're ranking last from the dropdown below, and work your way up. "
                    "You will be prompted to enter your commentary for each song.",
                color=0x3498db
            )
        return build_rankings_embed(self.ranked_submissions, all_ranked=not self.unranked_submissions)

    async def rank_song(self, interaction: discord.Interaction, song: Submission, commentary: str):
        """Records the listener's pick for the current rank. It is saved before the message is updated."""
        save_ranking_pick_db(self.round_id, song.user_id, self.current_rank, commentary)

        self.ranked_submissions.append(RankedSong(song, self.current_rank, commentary))
        self.unranked_submissions = [s for s in self.unranked_submissions if s.video_id != song.video_id]
        self.current_rank -= 1
        await self.update_ui(interaction)

    async def start_over(self, interaction: discord.Interaction):
        """Forgets every pick so far and shows the full list again."""
        clear_ranking_picks_db(self.round_id)
        self.ranked_submissions = []
        self.unranked_submissions = list(self.all_submissions)
        self.current_rank = len(self.all_submissions)
        await self.update_ui(interaction)

    async def update_ui(self, interaction: discord.Interaction):
        """Redraws the message with the current picks."""
        self.setup_select_menu()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

# Discord rejects an embed whose text adds up to more than 6000 characters. Stay a little under it.
EMBED_TEXT_BUDGET = 5800
FIELD_VALUE_LIMIT = 1024
MIN_PREVIEW_LENGTH = 60

def build_rankings_embed(ranked_songs: list[RankedSong], all_ranked: bool) -> discord.Embed:
    """
    The host's ranking summary. Long commentary is shortened in this preview so the embed always
    fits Discord's size limit; the full text is saved and published in the reveal.
    """
    title = "Listen Game Rankings"
    description = "✅ **All songs ranked!** Review your list and click Confirm to publish." if all_ranked \
        else "Here are your rankings so far:"

    names = [f"#{item.rank} - {item.submission.raw_title}"[:256] for item in ranked_songs]
    overhead = len(title) + len(description) + sum(len(name) for name in names) + 100
    per_field = FIELD_VALUE_LIMIT
    if ranked_songs:
        per_field = min(FIELD_VALUE_LIMIT, max(MIN_PREVIEW_LENGTH, (EMBED_TEXT_BUDGET - overhead) // len(names)))

    embed = discord.Embed(title=title, description=description, color=0x2ecc71 if all_ranked else 0x3498db)
    shortened = False
    for name, item in zip(names, ranked_songs):
        commentary = item.commentary
        if len(commentary) > per_field:
            commentary = commentary[:per_field - 1] + "…"
            shortened = True
        embed.add_field(name=name, value=commentary, inline=False)

    if shortened:
        embed.set_footer(text="Long commentary is shortened in this preview. The full text will be published.")
    return embed

class RankSingleSongButton(Button):
    """Button fallback for when there is only one song left to rank."""

    def __init__(self, submission: Submission, current_rank: int):
        # Truncate the title to avoid hitting Discord's 80-character limit for button labels
        label_text = f"Rank #{current_rank}: {submission.raw_title[:60]}"
        super().__init__(label=label_text, style=discord.ButtonStyle.primary)
        self.submission = submission
        self.current_rank = current_rank

    async def callback(self, interaction: discord.Interaction):
        # Launch the modal just like the Select menu does
        modal = CommentaryModal(self.view, self.submission, self.current_rank)
        await interaction.response.send_modal(modal)
