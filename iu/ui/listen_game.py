"""UI elements for the listen game"""
import logging

import asyncio
import discord
from discord.ui import View, Select, Modal, TextInput, Button
from db.listen_game import (
    get_game_by_status_db, register_player_db, save_round_results_db,
    advance_game_turn_db, unregister_player_db, get_registered_players_db,
    set_round_theme_db, get_game_leaderboard_db, update_round_status_message_db,
    update_round_ruleset_message_db, get_game_rounds_db
)
from utils.strings import get_ordinal, generate_leaderboard_text

logger = logging.getLogger('iu-bot')

class JoinGameView(discord.ui.View):
    """UI view for the join game button"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, custom_id="leave_listen_game")
    async def leave_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        game = get_game_by_status_db('registration')
        if not game:
            await interaction.response.send_message("⚠️ No registration session is active.", ephemeral=True)
            return

        success = unregister_player_db(game['game_id'], interaction.user.id)
        if not success:
            await interaction.response.send_message("You aren't registered for this game.", ephemeral=True)
            return

        # Re-fetch state and instantly overwrite the embed message layout
        await self._refresh_roster_embed(interaction, game)

    @discord.ui.button(label="Join Listen Game!", style=discord.ButtonStyle.primary, custom_id="join_listen_game")
    async def join_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        game = get_game_by_status_db('registration')
        if not game:
            await interaction.response.send_message("⚠️ No registration session is active.", ephemeral=True)
            return

        success = register_player_db(game['game_id'], interaction.user.id)
        if not success:
            await interaction.response.send_message("You are already registered!", ephemeral=True)
            return

        # Handle backend role assignment
        if interaction.guild and isinstance(interaction.user, discord.Member):
            target_role = discord.utils.get(interaction.guild.roles, name="Listen Game Player")
            if target_role and target_role not in interaction.user.roles:
                try:
                    await interaction.user.add_roles(target_role)
                except discord.Forbidden:
                    logger.error("Error: Bot lacks permission to assign the role.")
                except discord.HTTPException as ex:
                    logger.error("HTTPException while assigning role: %s", ex)

        # Re-fetch state and overwrite the embed message layout
        await self._refresh_roster_embed(interaction, game)

    async def _refresh_roster_embed(self, interaction: discord.Interaction, game: dict):
        """Helper function to recalculate the roster and update the embed."""
        players = get_registered_players_db(game['game_id'])
        max_round_days = game.get('max_round_days')
        deadline_text = f"**Max Round Duration:** {max_round_days} Days" if max_round_days \
            else "**Max Round Duration:** None (GM Managed)"

        # Rebuild the base embed layout
        gm_mention = f"<@{game['gm_id']}>"
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

class SetThemeModal(discord.ui.Modal, title='Set Listen Game Ruleset'):
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
        success = set_round_theme_db(self.round_id, self.theme_text.value)
        if not success:
            await interaction.response.send_message(
                "❌ Failed to save the ruleset. Please contact the GM.", ephemeral=True)
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
        target_role = discord.utils.get(interaction.guild.roles, name="Listen Game Player")
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
            except Exception as e:
                logger.warning("Failed to fetch and save ruleset message ID: %s", e)

            players = get_registered_players_db(self.game_id)
            total_needed = len(players) - 1

            # Post the initial tracker message
            tracker_msg = await interaction.channel.send(
                f"🎧 **Round Status:** We are at `0/{total_needed}` submissions for the round."
            )

            # Save it to the DB
            update_round_status_message_db(self.round_id, tracker_msg.id)


class CommentaryModal(Modal):
    """UI modal for letting the play add commentary for a ranking"""

    def __init__(self, view_instance: View, selected_song: dict, current_rank: int):
        super().__init__(title=f"{get_ordinal(current_rank)} Place Commentary")
        self.view_instance = view_instance
        self.selected_song = selected_song

        self.commentary = TextInput(
            label=f"For {selected_song['raw_title'][:37]}",
            style=discord.TextStyle.paragraph,
            placeholder="Share your thoughts here!",
            required=True,
            max_length=1000
        )
        self.add_item(self.commentary)

    # pylint: disable=arguments-differ
    async def on_submit(self, interaction: discord.Interaction):
        # Save the result to the View's state
        self.view_instance.ranked_submissions.append({
            "submission": self.selected_song,
            "rank": self.view_instance.current_rank,
            "commentary": self.commentary.value
        })

        # Remove from unranked list
        self.view_instance.unranked_submissions = [
            s for s in self.view_instance.unranked_submissions
            if s['video_id'] != self.selected_song['video_id']
        ]

        self.view_instance.current_rank += 1
        await self.view_instance.update_ui(interaction)


class RankingSelect(Select):
    """UI for the selector to choose songs to rank"""

    def __init__(self, unranked_submissions: list, current_rank: int):
        options = []
        for sub in unranked_submissions:
            options.append(discord.SelectOption(
                label=sub['raw_title'][:100],
                value=sub['video_id']
            ))

        super().__init__(
            placeholder=f"Select your pick for Rank #{current_rank}...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_video_id = self.values[0]
        selected_song = next(s for s in self.view.unranked_submissions if s['video_id'] == selected_video_id)

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
        await interaction.response.defer()

        total_submissions = len(self.view.ranked_submissions)
        results_to_save = []

        for item in self.view.ranked_submissions:
            results_to_save.append({
                "user_id": item['submission']['user_id'],
                "rank": item['rank'],
                "points": total_submissions - item['rank'] + 1,
                "commentary": item['commentary'],
                "raw_title": item['submission']['raw_title'],
                "video_id": item['submission']['video_id']
            })

        success = save_round_results_db(self.game_id, self.round_id, results_to_save)
        if not success:
            await interaction.followup.send("❌ Error saving results to the database. Aborting reveal.", ephemeral=True)
            return

        await interaction.followup.send("✅ Results locked in! The reveal is starting in the game channel.",
                                        ephemeral=True)

        channel = interaction.client.get_channel(self.listen_channel_id)
        if not channel:
            return

        player_role = discord.utils.get(interaction.guild.roles, name='Listen Game Player')
        await channel.send(
            f"🎧 **{player_role.mention}, {interaction.user.mention} has finished their rankings! "
            "Here are the results:**")
        await asyncio.sleep(15)

        reversed_reveals = sorted(results_to_save, key=lambda x: x['rank'], reverse=True)
        for result in reversed_reveals:
            rank_str = get_ordinal(result['rank'])
            title = result['raw_title']
            url = f"https://youtu.be/{result['video_id']}"
            commentary = result['commentary']

            msg = f"**{rank_str}: [{title}](<{url}>)**\n{commentary}"
            await channel.send(msg)
            await asyncio.sleep(15)

        next_host_id = advance_game_turn_db(self.game_id, self.round_id)

        # Build Last Round's Results
        sorted_round = sorted(results_to_save, key=lambda x: x['rank'])
        summary_lines = ["**Last Round's Results**"]
        for result in sorted_round:
            rank_str = get_ordinal(result['rank'])
            user_mention = f"<@{result['user_id']}>"
            title = result['raw_title']
            pts = result['points']
            summary_lines.append(f"{rank_str}: {user_mention} - **{title}** ({pts} pts)")

        # Build Current Ranking
        leaderboard = get_game_leaderboard_db(self.game_id)
        ranking_lines = ["**Current Ranking**"]

        if leaderboard:
            for idx, entry in enumerate(leaderboard):
                rank_str = get_ordinal(idx + 1)
                u_id = entry.get('user_id', entry.get('id'))
                score = entry.get('total_points', entry.get('score', entry.get('points', 0)))

                ranking_lines.append(f"{rank_str} - <@{u_id}> ({score} pts)")
        else:
            ranking_lines.append("*Error fetching leaderboard.*")

        # Combine and Send
        summary_text = "\n".join(summary_lines)
        ranking_text = "\n".join(ranking_lines)
        message_str = f"🎉 **Round complete!**\n\n{summary_text}\n\n{ranking_text}\n\n"
        if next_host_id:
            message_str += f"The next listener is <@{next_host_id}>! Use `/listen-game-post-ruleset` " \
                "when you are ready to begin."

        # Send last round's results
        await channel.send(message_str)

        # The game is over
        if not next_host_id:
            await channel.send(generate_leaderboard_text(leaderboard))

            # Send the compilation of all playlists
            rounds = get_game_rounds_db(self.game_id)
            if rounds:
                playlist_lines = ["🎶 **Here's all of the playlists from this game:**"]
                for i, r_data in enumerate(rounds, start=1):
                    host_mention = f"<@{r_data['host_id']}>"

                    if r_data['playlist_id']:
                        playlist_url = f"https://www.youtube.com/playlist?list={r_data['playlist_id']}"
                    else:
                        playlist_url = "*No playlist generated*"

                    playlist_lines.append(f"**Round {i}** ({host_mention}): {playlist_url}")

                # Add a slight delay so it posts cleanly after the leaderboard
                await asyncio.sleep(2)
                await channel.send("\n".join(playlist_lines))


class ListenGameRankingView(View):
    """Interactive view managing the draft-style ranking process."""

    def __init__(self, submissions: list, game_id: int, round_id: int, listen_channel_id: int):
        super().__init__(timeout=None)
        self.unranked_submissions = submissions
        self.ranked_submissions = []
        self.current_rank = 1

        # Store the IDs in the View
        self.game_id = game_id
        self.round_id = round_id
        self.listen_channel_id = listen_channel_id

        self.setup_select_menu()

    def setup_select_menu(self):
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

    async def update_ui(self, interaction: discord.Interaction):
        self.setup_select_menu()

        embed = discord.Embed(
            title="Listen Game Rankings",
            description="Here are your rankings so far:",
            color=0x3498db
        )

        for item in self.ranked_submissions:
            song_title = item['submission']['raw_title']
            embed.add_field(
                name=f"#{item['rank']} - {song_title}",
                value=f"*{item['commentary']}*",
                inline=False
            )

        if not self.unranked_submissions:
            embed.description = "✅ **All songs ranked!** Review your list and click Confirm to publish."
            embed.color = 0x2ecc71

        await interaction.response.edit_message(embed=embed, view=self)

class RankSingleSongButton(Button):
    """Button fallback for when there is only one song left to rank."""

    def __init__(self, submission: dict, current_rank: int):
        # Truncate the title to avoid hitting Discord's 80-character limit for button labels
        label_text = f"Rank #{current_rank}: {submission['raw_title'][:60]}"
        super().__init__(label=label_text, style=discord.ButtonStyle.primary)
        self.submission = submission
        self.current_rank = current_rank

    async def callback(self, interaction: discord.Interaction):
        # Launch the modal just like the Select menu does
        modal = CommentaryModal(self.view, self.submission, self.current_rank)
        await interaction.response.send_modal(modal)
