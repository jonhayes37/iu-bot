"""The IU Discord client: intents, command registration, startup and event routing."""

import logging

import discord

from commands.registry import all_commands
from config import Channel, guild_id
from db.bot import get_active_bot_status_db
from tasks.heartbeat import write_heartbeat
from tasks.listen_game import check_listen_game_reminders
from tasks.scheduled_events import check_upcoming_events
from tasks.tournaments import tournament_resolution_loop
from triggers.member import add_trainee_role, welcome_member
from triggers.merch import handle_reaction_add
from triggers.message import check_message_for_replies, respond_to_ping
from triggers.polls import handle_poll_vote, handle_poll_vote_remove
from triggers.releases import store_new_release
from triggers.roles import handle_role_assignment
from triggers.scheduled_events import process_event
from ui.base import report_interaction_error
from ui.eoy_nominations import HallOfFameNominationButton, Top25Button
from ui.eoy_voting import HallOfFameVoteButton, HMAVoteButton
from ui.hma_suggestions import HMASuggestButton
from ui.listen_game import JoinGameView
from ui.lists import SubmitListButton

logger = logging.getLogger('iu-bot')


async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """Reports a failed slash command to the user instead of leaving the interaction hanging."""
    # Check for missing role
    if isinstance(error, discord.app_commands.errors.MissingRole):
        await interaction.response.send_message(
            f"❌ You must have the '{error.missing_role}' role to use this command.",
            ephemeral=True
        )
    elif isinstance(error, discord.app_commands.errors.MissingPermissions):
        await interaction.response.send_message(
            "❌ Only server administrators can use this command.", ephemeral=True
        )
    else:
        # Logs the traceback and tells the user (database failures get their own message)
        await report_interaction_error(interaction, error)


class IUBot(discord.Client):
    """The bot. Creating one has no side effects; nothing connects until run() is called."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        # Added reactions intent so the bot can see when people add the merch-booth emoji!
        intents.reactions = True
        super().__init__(intents=intents)

        self.tree = discord.app_commands.CommandTree(self)
        self.tree.on_error = on_app_command_error
        for command in all_commands():
            self.tree.add_command(command)

    async def setup_hook(self):
        """Runs once per process, after login and before connecting (unlike on_ready, which reruns on reconnects)."""
        self._register_persistent_views()
        await self._sync_commands()

    def _register_persistent_views(self):
        """
        Re-attaches the buttons on old messages so they keep working after a restart. The buttons
        that carry a year or an event in their ID are dynamic items: registering the class once covers
        every year and every event, including messages posted before this restart.
        """
        self.add_dynamic_items(
            SubmitListButton, Top25Button, HallOfFameNominationButton,
            HallOfFameVoteButton, HMAVoteButton, HMASuggestButton
        )
        self.add_view(JoinGameView())
        logger.info("Persistent buttons registered.")

    async def _sync_commands(self):
        # A failed sync shouldn't stop the bot from starting; it just keeps the previous command list
        try:
            if guild_id():
                guild = discord.Object(id=guild_id())
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info("Command tree synced to guild %s", guild_id())
            else:
                logger.info("⚠️ Global sync triggered (May take 24 hours).")
                await self.tree.sync()
        except discord.HTTPException as e:
            logger.error("Failed to sync commands; Discord keeps showing the previous list: %s", e)

    async def on_ready(self):
        logger.info('%s has connected to Discord!', self.user)

        # The healthcheck reads this, so it runs even when no server is configured
        if not write_heartbeat.is_running():
            write_heartbeat.start(self)

        if not guild_id():
            return

        # Start the background tasks (on_ready can fire again after a reconnect, so don't restart them)
        if not check_upcoming_events.is_running():
            check_upcoming_events.start(self, guild_id())
            logger.info("Event notifier task started.")

        if not tournament_resolution_loop.is_running():
            tournament_resolution_loop.start(self, guild_id())
            logger.info("Tournament resolution task started.")

        if not check_listen_game_reminders.is_running():
            check_listen_game_reminders.start(self, guild_id())
            logger.info("Listen game reminder task started.")

        # Set the bot's status
        saved_status = get_active_bot_status_db()
        if saved_status:
            activity = discord.Activity(type=discord.ActivityType.listening, name=saved_status)
            await self.change_presence(status=discord.Status.online, activity=activity)
        else:
            await self.change_presence(status=discord.Status.online, activity=None)

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

        # Other bots (and webhooks) never get a reply, so two bots can't set each other off
        if self.user.mentioned_in(message) and not message.author.bot:
            await respond_to_ping(message)

        if message.guild:
            channel_name = message.channel.name

            if channel_name == Channel.NEW_RELEASES:
                await store_new_release(message)

            if channel_name == Channel.ROLES:
                await handle_role_assignment(message)
                # Roles shouldn't trigger IU replies
                return

            if channel_name == Channel.DISPATCH_NEWS:
                # dispatch-news is for bot announcements, so we don't want IU to reply to messages here
                return

        if not message.author.bot:
            await check_message_for_replies(message)

    async def on_member_join(self, member: discord.Member):
        await add_trainee_role(member)
        await welcome_member(member)

    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        """Fires automatically whenever someone creates a new native event."""
        await process_event(event, is_update=False)

    async def on_scheduled_event_update(self, _: discord.ScheduledEvent, after: discord.ScheduledEvent):
        # Pass the 'after' object so we operate on the newest data
        await process_event(after, is_update=True)

    async def on_raw_poll_vote_add(self, payload: discord.RawPollVoteActionEvent):
        await handle_poll_vote(self, payload)

    async def on_raw_poll_vote_remove(self, payload: discord.RawPollVoteActionEvent):
        await handle_poll_vote_remove(self, payload)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await handle_reaction_add(payload, self)
