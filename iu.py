"""IU Bot for the HallyU Discord server"""

import os

import discord
import typing
from dotenv import load_dotenv

from commands.bias_group import my_bias_group
from commands.calendar import send_calendar
from commands.ultimate_bias import my_ultimate_bias
from triggers.message import check_message_for_replies, respond_to_ping
from triggers.member import add_trainee_role, welcome_member

# Load env vars, connect to Discord
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD')
CHANNELS = {
    'introductions': os.getenv('DISCORD_CHANNEL_INTRODUCTIONS'),
    'roles': os.getenv('DISCORD_CHANNEL_ROLES'),
    'rules': os.getenv('DISCORD_CHANNEL_RULES'),
    'welcome': os.getenv('DISCORD_CHANNEL_WELCOME')
}

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

# client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')
    await tree.sync()
    print(f'Command tree synced!')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if client.user.mentioned_in(message):
        await respond_to_ping(message)

    await check_message_for_replies(message)

@client.event
async def on_member_join(member):
    await add_trainee_role(member)
    await welcome_member(member)

@tree.command(name='my-ultimate-bias', description="See who everyone's ultimate bias is!")
@discord.app_commands.describe(member='The member whose bias you want to see. Leave empty for your own.')
async def ultimate_bias(interaction, member: typing.Optional[str]):
    await my_ultimate_bias(interaction, member)

@tree.command(name='my-bias-group', description="See who everyone's bias group is!")
@discord.app_commands.describe(member='The member whose bias group you want to see. Leave empty for your own.')
async def bias_group(interaction, member: typing.Optional[str]):
    await my_bias_group(interaction, member)

@tree.command(name='hallyu-calendar', description="See how to add the HallyU calendar to your own calendar.")
async def hallyu_calendar(interaction):
    await send_calendar(interaction)

client.run(TOKEN)
