"""IU Bot for the HallyU Discord server"""

import logging
import os
import typing
import sqlite3

import discord
from commands.bias_group import my_bias_group
from commands.calendar import send_calendar
from commands.hmas import add_hma_pick, delete_hma_picks, my_hma_picks
from commands.merch_admin import admin_modify_balance, admin_random_award, admin_add_merch, admin_set_status
from commands.merch_user import user_check_balance, user_view_merch, user_purchase_merch, user_purchase_history
from commands.poll import generate_poll
from commands.releases_backfill import backfill_releases
from commands.rankdown_turn import (InvalidSongError,
                                    SamePlayerEliminationError, rankdown_turn)
from commands.ultimate_bias import my_ultimate_bias
from dotenv import load_dotenv
from triggers.member import add_trainee_role, welcome_member
from triggers.merch import handle_reaction_add
from triggers.message import check_message_for_replies, respond_to_ping, store_new_release

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('iu-bot')

# Load env vars
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD')
COMMAND_ERRORS = [InvalidSongError, SamePlayerEliminationError]

# Database setup
DB_PATH_MERCH = os.getenv('DB_PATH_MERCH')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH_MERCH = os.path.join(BASE_DIR, "merch_schema.sql")

def initialize_database():
    """Reads the schema.sql file and executes it to ensure all tables exist."""
    logger.info("Initializing database...")

    # Ensure the directory exists (crucial for Docker bind mounts)
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH_MERCH)), exist_ok=True)

    # Read the SQL blueprint
    try:
        with open(SCHEMA_PATH_MERCH, 'r', encoding='utf-8') as file:
            schema_script = file.read()
    except FileNotFoundError:
        logger.critical("Error: Could not find schema file at %s", SCHEMA_PATH_MERCH)
        return

    # Connect to the DB and execute the script
    with sqlite3.connect(DB_PATH_MERCH) as conn:
        conn.executescript(schema_script)
        conn.commit()

    logger.info("Database initialized successfully at %s", DB_PATH_MERCH)

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
        guild = discord.Object(id=int(GUILD))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        logger.info("Command tree synced to Guild %s", GUILD)
    else:
        logger.info("⚠️ Global sync triggered (May take 24 hours).")
        await tree.sync()

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user.mentioned_in(message):
        await respond_to_ping(message)

    releases_channel = discord.utils.get(message.guild.text_channels, name='new-releases')
    if message.channel == releases_channel:
        store_new_release(message)

    await check_message_for_replies(message)

@client.event
async def on_member_join(member):
    await add_trainee_role(member)
    await welcome_member(member)

# Commands
@tree.command(name='backfill-new-releases', description="[INTERNAL ONLY] Backfills new releases")
async def backfill(interaction):
    channel = discord.utils.get(interaction.guild.text_channels, name='new-releases')
    await backfill_releases(channel)

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

@tree.command(name='hallyu-calendar', description="See how to add the HallyU calendar " \
              "to your own calendar.")
async def hallyu_calendar(interaction):
    await send_calendar(interaction)

@tree.command(name='poll', description="Create a poll.")
@discord.app_commands.describe(question='The question you want to ask',
                               answers='The possible answers, separated by |')
async def poll(interaction, question: str, answers: str):
    await generate_poll(interaction, question, answers)

@tree.command(name='rankdown-turn', description="Take your turn in Rankdown")
@discord.app_commands.describe(song_to_eliminate="The song you're eliminating",
                               reason_to_eliminate="Why you're eliminating the song",
                               song_to_nominate="The song you're nominating",
                               reason_to_nominate="Why you're nominating the song",
                               next_message="The message for the next player")
async def rankdown(interaction, song_to_eliminate: str, reason_to_eliminate: str,
               song_to_nominate: str, reason_to_nominate: str, next_message: typing.Optional[str]):
    await rankdown_turn(interaction, song_to_eliminate, reason_to_eliminate,
                        song_to_nominate, reason_to_nominate, next_message)

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
    await user_check_balance(interaction)

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

# Run database setup before starting the bot
initialize_database()
client.run(TOKEN)
