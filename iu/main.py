"""IU Bot for the HallyU Discord server"""

import logging
import os
import typing
import sqlite3

import discord
from commands.bias_group import my_bias_group
from commands.hmas import add_hma_pick, delete_hma_picks, my_hma_picks
from commands.lists import handle_create_list_event, handle_close_list_event, handle_export_lists
from commands.merch_admin import admin_modify_balance, admin_random_award, admin_add_merch, admin_set_status
from commands.merch_user import user_check_balance, user_view_merch, user_purchase_merch, user_purchase_history
from commands.poll import generate_poll
from commands.releases_backfill import backfill_releases
from commands.roles import handle_register_role
from commands.ultimate_bias import my_ultimate_bias
from dotenv import load_dotenv
from tasks.scheduled_events import check_upcoming_events
from triggers.member import add_trainee_role, welcome_member
from triggers.merch import handle_reaction_add
from triggers.message import check_message_for_replies, respond_to_ping
from triggers.releases import store_new_release
from triggers.roles import handle_role_assignment
from ui.lists import handle_list_button_click

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('iu-bot')

# Load env vars
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD')

# Database setup
DB_PATH_MERCH = os.getenv('DB_PATH_MERCH')
DB_PATH_RELEASES = os.getenv('DB_PATH_RELEASES')
DB_PATH_ROLES = os.getenv('DB_PATH_ROLES')
DB_PATH_LISTS = os.getenv('DB_PATH_LISTS')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH_MERCH = os.path.join(BASE_DIR, "db/schema/merch.sql")
SCHEMA_PATH_RELEASES = os.path.join(BASE_DIR, "db/schema/releases.sql")
SCHEMA_PATH_ROLES = os.path.join(BASE_DIR, "db/schema/roles.sql")
SCHEMA_PATH_LISTS = os.path.join(BASE_DIR, "db/schema/lists.sql")

def initialize_database():
    """Reads the schema.sql file and executes it to ensure all tables exist."""
    logger.info("Initializing database...")

    # Ensure the directory exists (crucial for Docker bind mounts)
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH_MERCH)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH_RELEASES)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH_ROLES)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH_LISTS)), exist_ok=True)

    # Read the SQL blueprint
    try:
        with open(SCHEMA_PATH_MERCH, 'r', encoding='utf-8') as file:
            merch_schema_script = file.read()
        with open(SCHEMA_PATH_RELEASES, 'r', encoding='utf-8') as file:
            releases_schema_script = file.read()
        with open(SCHEMA_PATH_ROLES, 'r', encoding='utf-8') as file:
            roles_schema_script = file.read()
        with open(SCHEMA_PATH_LISTS, 'r', encoding='utf-8') as file:
            lists_schema_script = file.read()
    except FileNotFoundError:
        logger.critical("Error: Could not find schema file at %s", SCHEMA_PATH_MERCH)
        return

    # Connect to the DB and execute the script
    with sqlite3.connect(DB_PATH_MERCH) as conn:
        conn.executescript(merch_schema_script)
        conn.commit()
    logger.info("Database initialized successfully at %s", DB_PATH_MERCH)

    with sqlite3.connect(DB_PATH_RELEASES) as conn:
        conn.executescript(releases_schema_script)
        conn.commit()
    logger.info("Database initialized successfully at %s", DB_PATH_RELEASES)

    with sqlite3.connect(DB_PATH_ROLES) as conn:
        conn.executescript(roles_schema_script)
        conn.commit()
    logger.info("Database initialized successfully at %s", DB_PATH_ROLES)

    with sqlite3.connect(DB_PATH_LISTS) as conn:
        conn.executescript(lists_schema_script)
        conn.commit()
    logger.info("Database initialized successfully at %s", DB_PATH_LISTS)

# Connect to Discord
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
# Added reactions intent so the bot can see when people add the merch-booth emoji!
intents.reactions = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

@client.event
async def on_ready():
    logger.info('%s has connected to Discord!', client.user)

    if GUILD:
        # Start the event background task
        if not check_upcoming_events.is_running():
            check_upcoming_events.start(client, int(GUILD))
            logger.info("Event notifier task started.")

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
        sandbox_channel = discord.utils.get(message.guild.text_channels, name='sandbox')
        releases_channel = discord.utils.get(message.guild.text_channels, name='new-releases')
        roles_channel = discord.utils.get(message.guild.text_channels, name='roles')

        if message.channel in [releases_channel, sandbox_channel]:
            await store_new_release(message)

        if message.channel == roles_channel:
            await handle_role_assignment(message)
            # Roles shouldn't trigger IU replies
            return

    await check_message_for_replies(message)

@client.event
async def on_member_join(member):
    await add_trainee_role(member)
    await welcome_member(member)

@client.event
async def on_scheduled_event_create(event: discord.ScheduledEvent):
    """Fires automatically whenever someone creates a new native event."""
    channel = discord.utils.get(event.guild.text_channels, name='community-events')
    if not channel:
        logger.error("Could not find #community-events channel.")
        return

    role = discord.utils.get(event.guild.roles, name='Watch Parties')
    if not role:
        logger.error("Could not find Watch Parties role.")
        return

    creator = event.creator.mention
    await channel.send(
        f"{role.mention} **{event.name}** has been scheduled by {creator}! "
        f"RSVP below so you don't miss out!\n\n{event.url}"
    )

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

    # Let discord.py continue processing normal slash commands
    if hasattr(client, 'process_commands'):
        await client.process_commands(interaction)

@tree.command(name='backfill-new-releases', description="[Admin] Backfills new releases from a specific date")
@discord.app_commands.describe(start_date="The start date for the backfill in YYYY-MM-DD format (e.g., 2025-12-01)")
@discord.app_commands.default_permissions(administrator=True)
async def backfill(interaction: discord.Interaction, start_date: str):
    channel = discord.utils.get(interaction.guild.text_channels, name='new-releases')
    if not channel:
        return await interaction.response.send_message("Could not find the #new-releases channel.", ephemeral=True)

    await backfill_releases(interaction, channel, start_date)

@tree.command(name='my-ultimate-bias', description="See who everyone's ultimate bias is!")
@discord.app_commands.describe(member='The member whose bias you want to see. ' \
                               'Leave empty for your own.')
async def ultimate_bias(interaction, member: typing.Optional[str]):
    await my_ultimate_bias(interaction, member)

@tree.command(name='my-bias-group', description="See who everyone's bias group is!")
@discord.app_commands.describe(member='The member whose bias group you want to see.' \
                               'Leave empty for your own.')
async def bias_group(interaction, member: typing.Optional[str]):
    await my_bias_group(interaction, member)

@tree.command(name='poll', description="Create a poll.")
@discord.app_commands.describe(question='The question you want to ask',
                               answers='The possible answers, separated by |')
async def poll(interaction, question: str, answers: str):
    await generate_poll(interaction, question, answers)

@tree.command(name='add-hma-pick', description="Save something you want to remember for the HMAs!")
@discord.app_commands.describe(pick='The message and/or link you want to remember')
async def save_pick(interaction, pick: str):
    await add_hma_pick(interaction, pick)

@tree.command(name='delete-hma-picks', description="Delete your HMA picks to start fresh")
async def delete_picks(interaction):
    await delete_hma_picks(interaction)

@tree.command(name='my-hma-picks', description="See your saved HMA picks")
async def see_picks(interaction):
    await my_hma_picks(interaction)

# Merch triggers and commands
@client.event
async def on_raw_reaction_add(payload):
    # Delegate the logic to your external file
    await handle_reaction_add(payload, client)

@tree.command(name='modify-balance', description="[Admin only] Modify a user's heart balance.")
@discord.app_commands.describe(
    member="The server member to modify",
    amount="The number of hearts to add (use negative to subtract)",
    reason="Why this modification is being made (for the audit log)"
)
@discord.app_commands.default_permissions(administrator=True)
async def modify_balance(interaction: discord.Interaction, member: discord.Member, amount: int,
                         reason: str):
    await admin_modify_balance(interaction, member, amount, reason)

@tree.command(name='random-award',
              description="[Admin] Picks a random user from a list to win hearts!")
@discord.app_commands.describe(
    users="Mention the users to include (e.g., @Alice @Bob @Charlie)",
    amount="The number of hearts to award the winner",
    reason="What this award is for (e.g., Watch Party Attendee)"
)
@discord.app_commands.default_permissions(administrator=True)
async def random_award(interaction: discord.Interaction, users: str, amount: int, reason: str):
    await admin_random_award(interaction, users, amount, reason)

@tree.command(name='add-merch', description="[Admin] Add or update an item in the Merch Booth.")
@discord.app_commands.describe(
    item_id="A short, unique code (e.g., CUSTEMOJI)",
    name="The display name of the perk",
    description="What the user actually gets",
    price="Cost in hearts",
    max_per_user="Optional: Maximum times a single user can buy this"
)
@discord.app_commands.default_permissions(administrator=True)
async def add_merch(
    interaction: discord.Interaction,
    item_id: str,
    name: str,
    description: str,
    price: int,
    max_per_user: typing.Optional[int]
):
    await admin_add_merch(interaction, item_id, name, description, price, max_per_user)

@tree.command(name='check-balance',
              description="Check how many hearts you have available to spend.")
async def check_balance(interaction: discord.Interaction):
    await user_check_balance(logger, interaction)

@tree.command(name='view-merch', description="Browse the available perks in the merch stand!")
async def view_merch(interaction: discord.Interaction):
    await user_view_merch(interaction)

@tree.command(name='purchase', description="Buy something from the merch booth!")
@discord.app_commands.describe(
    item_id="The short code of the item you want to buy (e.g., CUSTEMOJI)")
async def purchase(interaction: discord.Interaction, item_id: str):
    await user_purchase_merch(interaction, item_id)

@tree.command(name='purchase-history', description="View all of the merch you've bought!")
async def purchase_history(interaction: discord.Interaction):
    await user_purchase_history(interaction)

@tree.command(name='set-status',
              description="[Admin] Change IU's status message for a specific user's perk.")
@discord.app_commands.describe(
    member="The user who purchased the status perk",
    status_text="The text to display after 'Listening to'"
)
@discord.app_commands.default_permissions(administrator=True)
async def set_status(interaction: discord.Interaction, member: discord.Member, status_text: typing.Optional[str]):
    await admin_set_status(interaction, member, status_text)

@tree.command(name='register-role', description="[Admin] Add a new assignable role to the #roles channel.")
@discord.app_commands.default_permissions(administrator=True)
async def register_role(
    interaction: discord.Interaction,
    role: discord.Role,
    category: str,
    aliases: str = ""  # Making it optional in the Discord UI
):
    await handle_register_role(interaction, role, category, aliases)

@tree.command(name='create-list-event', description="[Admin] Start a new list submission event.")
@discord.app_commands.default_permissions(administrator=True)
async def create_list_event(
    interaction: discord.Interaction,
    event_id: str,
    event_name: str,
    expected_count: int = 0,
    placeholder: str = "1. Berry Good // Don't Believe\n2. IVE // All Night (https://youtu.be/xU8mQMLx0tk?t=27)\n..."
):
    await handle_create_list_event(interaction, event_id, event_name, expected_count, placeholder)

@tree.command(name='close-list-event', description="[Admin] Close an active list event and disable its button.")
@discord.app_commands.default_permissions(administrator=True)
async def close_list_event(
    interaction: discord.Interaction,
    event_id: str
):
    # Notice we removed message_id here, since the DB handles it now!
    await handle_close_list_event(interaction, event_id)

@tree.command(name='export-lists',
              description="[Admin] Export all list submissions for a specific event to .csv and .txt files.")
@discord.app_commands.default_permissions(administrator=True)
async def export_lists(interaction: discord.Interaction, event_id: str):
    await handle_export_lists(interaction, event_id)

# Run database setup before starting the bot
initialize_database()
client.run(TOKEN)
