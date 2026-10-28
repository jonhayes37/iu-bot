"""The IU Discord client: intents, command registration, startup and event routing."""

import logging

import discord

from commands.registry import all_commands
from config import Channel, guild_id
from tasks.heartbeat import write_heartbeat
from tasks.listen_game import check_listen_game_reminders
from tasks.scheduled_events import check_upcoming_events
from tasks.secret_polls import close_secret_polls
from tasks.status import refresh_status, show_saved_status
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
from ui.hma_nominations import HMANominationsButton, NominationPageButton
from ui.hma_suggestions import HMASuggestButton
from ui.listen_game import JoinGameView
from ui.lists import SubmitListButton
from ui.secret_poll import SecretVoteButton

logger = logging.getLogger('iu-bot')


COMMAND_OUT_OF_DATE = (
    "⚠️ Discord's copy of this command is out of date, so it couldn't run and nothing was changed. Try again "
    "in a minute; if it keeps happening, reload Discord (Ctrl+R, or close and reopen the app)."
)


def _explain_refusal(error: discord.app_commands.AppCommandError) -> str | None:
    """
    What to tell the user when a command was refused before it ran (a check or an option failed, or
    Discord's list of commands doesn't match the bot's), or None if the command itself failed.
    """
    if isinstance(error, discord.app_commands.MissingRole):
        return f"❌ You must have the '{error.missing_role}' role to use this command."
    if isinstance(error, discord.app_commands.MissingPermissions):
        return "❌ Only server administrators can use this command."
    if isinstance(error, discord.app_commands.TransformerError):
        if error.type is discord.AppCommandOptionType.user:
            # A member option names someone who has left the server since (Discord still offers them)
            who = getattr(error.value, "mention", "That person")
            return f"❌ {who} isn't in the server any more, so this command can't be used on them."
        return f"❌ I couldn't understand one of the options you gave (`{error.value}`). Check it and try again."
    if isinstance(error, (discord.app_commands.CommandNotFound, discord.app_commands.CommandSignatureMismatch)):
        # Usually a command sync that failed or hasn't reached this member's Discord yet
        logger.warning("Discord's command list doesn't match the bot's: %s", error)
        return COMMAND_OUT_OF_DATE
    return None


async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """Reports a failed slash command to the user instead of leaving the interaction hanging."""
    text = _explain_refusal(error)
    if text is None:
        # Logs the traceback and tells the user (database failures get their own message)
        await report_interaction_error(interaction, error)
        return

    try:
        await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException as ex:
        logger.warning("Could not tell the user why a command was refused: %s", ex)


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
            HallOfFameVoteButton, HMAVoteButton, HMASuggestButton, SecretVoteButton,
            HMANominationsButton, NominationPageButton
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

        if not close_secret_polls.is_running():
            close_secret_polls.start(self)
            logger.info("Secret poll closing task started.")

        # Show the saved status, and keep it up to date (it goes away when it expires). The loop's first
        # run shows it; after a reconnect the loop is already running, so show it straight away.
        if not refresh_status.is_running():
            refresh_status.start(self)
            logger.info("Status refresh task started.")
        else:
            await show_saved_status(self)

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
