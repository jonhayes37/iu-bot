"""IU Bot for the HallyU Discord server"""

import logging
import os
import sqlite3

import discord
from commands.biases import (
    bias_group, create_bias_group, create_ultimate_bias, ultimate_bias,
    update_bias_group, update_ultimate_bias
)
from commands.listen_game import (
    listen_game_create, listen_game_start, listen_game_set_theme, submit_song,
    listen_game_submit_ranking
)
from commands.listen_game_gm import (
    listen_game_gm_sync_playlist, listen_game_gm_reject_song, listen_game_gm_skip_turn,
    listen_game_gm_remove_player, listen_game_gm_force_start_round, listen_game_gm_force_submit
)
from commands.lists import create_list_event, close_list_event, export_lists
from commands.hearts import check_balance, modify_balance, random_award
from commands.bot import set_iu_status
from commands.merch import add_merch, view_merch, purchase, purchase_history
from commands.releases import backfill_releases
from commands.roles import register_role, sync_roles
from commands.tournaments import force_close_round, new_tournament
from db.tournaments import process_user_vote
from db.merch import modify_db_balance
from tasks.listen_game import check_listen_game_reminders
from tasks.scheduled_events import check_upcoming_events
from tasks.tournaments import tournament_resolution_loop
from triggers.member import add_trainee_role, welcome_member
from triggers.merch import handle_reaction_add
from triggers.message import check_message_for_replies, respond_to_ping
from triggers.releases import store_new_release
from triggers.roles import handle_role_assignment
from triggers.scheduled_events import process_event
from ui.lists import handle_list_button_click

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('iu-bot')

# Load env vars
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD')
DB_PATH_BIASES = os.getenv('DB_PATH_BIASES')
DB_PATH_LISTEN_GAME = os.getenv('DB_PATH_LISTEN_GAME')
DB_PATH_LISTS = os.getenv('DB_PATH_LISTS')
DB_PATH_MERCH = os.getenv('DB_PATH_MERCH')
DB_PATH_RELEASES = os.getenv('DB_PATH_RELEASES')
DB_PATH_ROLES = os.getenv('DB_PATH_ROLES')
DB_PATH_TOURNAMENTS = os.getenv('DB_PATH_TOURNAMENTS')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH_BIASES = os.path.join(BASE_DIR, "db/schema/biases.sql")
SCHEMA_PATH_LISTEN_GAME = os.path.join(BASE_DIR, "db/schema/listen_game.sql")
SCHEMA_PATH_LISTS = os.path.join(BASE_DIR, "db/schema/lists.sql")
SCHEMA_PATH_MERCH = os.path.join(BASE_DIR, "db/schema/merch.sql")
SCHEMA_PATH_RELEASES = os.path.join(BASE_DIR, "db/schema/releases.sql")
SCHEMA_PATH_ROLES = os.path.join(BASE_DIR, "db/schema/roles.sql")
SCHEMA_PATH_TOURNAMENTS = os.path.join(BASE_DIR, "db/schema/tournaments.sql")

# Connect to Discord
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
# Added reactions intent so the bot can see when people add the merch-booth emoji!
intents.reactions = True

client = discord.Client(intents=intents)

# Configure all commands
tree = discord.app_commands.CommandTree(client)
# Bias cards
tree.add_command(bias_group)
tree.add_command(create_bias_group)
tree.add_command(create_ultimate_bias)
tree.add_command(update_bias_group)
tree.add_command(update_ultimate_bias)
tree.add_command(ultimate_bias)
# Bot management
tree.add_command(set_iu_status)
# Hearts
tree.add_command(check_balance)
tree.add_command(modify_balance)
tree.add_command(random_award)
# Listen Game
tree.add_command(listen_game_create)
tree.add_command(listen_game_start)
tree.add_command(listen_game_set_theme)
tree.add_command(submit_song)
tree.add_command(listen_game_submit_ranking)
# Listen Game (GM)
tree.add_command(listen_game_gm_sync_playlist)
tree.add_command(listen_game_gm_reject_song)
tree.add_command(listen_game_gm_skip_turn)
tree.add_command(listen_game_gm_remove_player)
tree.add_command(listen_game_gm_force_start_round)
tree.add_command(listen_game_gm_force_submit)
# Lists
tree.add_command(create_list_event)
tree.add_command(close_list_event)
tree.add_command(export_lists)
# Merch
tree.add_command(add_merch)
tree.add_command(purchase)
tree.add_command(purchase_history)
tree.add_command(view_merch)
# Releases
tree.add_command(backfill_releases)
# Roles
tree.add_command(register_role)
tree.add_command(sync_roles)
# Tournaments
tree.add_command(new_tournament)
tree.add_command(force_close_round)

@client.event
async def on_ready():
    logger.info('%s has connected to Discord!', client.user)

    if GUILD:
        # Start the background tasks
        if not check_upcoming_events.is_running():
            check_upcoming_events.start(client, int(GUILD))
            logger.info("Event notifier task started.")

        if not tournament_resolution_loop.is_running():
            tournament_resolution_loop.start(client, int(GUILD))
            logger.info("Tournament resolution task started.")

        if not check_listen_game_reminders.is_running():
            check_listen_game_reminders.start(client, int(GUILD))
            logger.info("Listen game reminder task started.")

        # Sync commands
        guild = discord.Object(id=int(GUILD))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        logger.info("Command tree synced to guild %s", GUILD)
    else:
        logger.info("⚠️ Global sync triggered (May take 24 hours).")
        await tree.sync()

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user.mentioned_in(message):
        await respond_to_ping(message)

    if message.guild:
        channel_name = message.channel.name

        if channel_name == 'new-releases':
            await store_new_release(message)

        if channel_name == 'roles':
            await handle_role_assignment(message)
            # Roles shouldn't trigger IU replies
            return

        if channel_name == 'dispatch-news':
            # dispatch-news is for bot announcements, so we don't want IU to reply to messages here
            return

    await check_message_for_replies(message)

@client.event
async def on_member_join(member):
    await add_trainee_role(member)
    await welcome_member(member)

@client.event
async def on_scheduled_event_create(event: discord.ScheduledEvent):
    """Fires automatically whenever someone creates a new native event."""
    await process_event(event, is_update=False)

@client.event
async def on_scheduled_event_update(_: discord.ScheduledEvent, after: discord.ScheduledEvent):
    # Pass the 'after' object so we operate on the newest data
    await process_event(after, is_update=True)

@client.event
async def on_raw_poll_vote_add(payload: discord.RawPollVoteActionEvent):
    # Ignore the bot's own interactions to prevent infinite loops
    if payload.user_id == client.user.id:
        return

    # Save the vote and check the ledger
    reward_data = process_user_vote(
        message_id=payload.message_id,
        user_id=payload.user_id,
        answer_id=payload.answer_id
    )

    # If reward_data exists, they successfully completed the round
    if reward_data:
        t_name = reward_data['tournament_name']
        r_num = reward_data['round_num']

        # Award the heart
        modify_db_balance("IU bot",
                          payload.user_id,
                          1,
                          f"Voted in every matchup for round {r_num} of **{t_name}**")

        # Post to #dispatch-news
        guild = client.get_guild(payload.guild_id)
        if not guild:
            return

        news_channel = discord.utils.get(guild.text_channels, name="dispatch-news")
        if news_channel:
            # Safely fetch the member to ping them
            member = await guild.fetch_member(payload.user_id)

            msg = (
                f"{member.mention} earned 1 heart for voting in every single "
                f"matchup for round {r_num} of **{t_name}**!"
            )
            await news_channel.send(msg)

@client.event
async def on_raw_reaction_add(payload):
    await handle_reaction_add(payload, client)

@client.event
async def on_interaction(interaction: discord.Interaction):
    # We only care about button clicks (Components)
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get('custom_id', '')

        # Catch our dynamic list submission buttons
        if custom_id.startswith('submit_list:'):
            # If the event is closed, the ID looks like submit_list:mid_2026_closed
            if custom_id.endswith('_closed'):
                await interaction.response.send_message("Submissions for this event are closed!", ephemeral=True)
                return

            # Extract the event_id (e.g., "mid_2026")
            event_id = custom_id.split(':')[1]
            await handle_list_button_click(interaction, event_id)
            return

def initialize_databases():
    """Dynamically reads and initializes all configured databases."""
    logger.info("Initializing databases...")
    db_configs = [
        (DB_PATH_BIASES, SCHEMA_PATH_BIASES),
        (DB_PATH_LISTEN_GAME, SCHEMA_PATH_LISTEN_GAME),
        (DB_PATH_LISTS, SCHEMA_PATH_LISTS),
        (DB_PATH_MERCH, SCHEMA_PATH_MERCH),
        (DB_PATH_RELEASES, SCHEMA_PATH_RELEASES),
        (DB_PATH_ROLES, SCHEMA_PATH_ROLES),
        (DB_PATH_TOURNAMENTS, SCHEMA_PATH_TOURNAMENTS)
    ]

    for db_path, schema_path in db_configs:
        if not db_path:
            logger.info("skipping database at %s", schema_path)
            continue

        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        try:
            with open(schema_path, 'r', encoding='utf-8') as file:
                schema_script = file.read()
            with sqlite3.connect(db_path) as conn:
                conn.executescript(schema_script)
                conn.commit()
        except FileNotFoundError:
            logger.critical("Error: Could not find schema file at %s", schema_path)
        except Exception as e:
            logger.error("Failed to initialize DB at %s: %s", db_path, e)

    logger.info("All databases initialized successfully.")

# Run database setup before starting the bot
initialize_databases()
client.run(TOKEN)
