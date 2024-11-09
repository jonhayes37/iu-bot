"""IU Bot for the HallyU Discord server"""

import os
import typing

import discord
from commands.bias_group import my_bias_group
from commands.calendar import send_calendar
from commands.hmas import add_hma_pick, delete_hma_picks, my_hma_picks
from commands.poll import generate_poll
from commands.releases_backfill import backfill_releases
from commands.rankdown_turn import (InvalidSongError,
                                    SamePlayerEliminationError, rankdown_turn)
from commands.ultimate_bias import my_ultimate_bias
from dotenv import load_dotenv
from triggers.member import add_trainee_role, welcome_member
from triggers.message import check_message_for_replies, respond_to_ping, store_new_release

# Load env vars, connect to Discord
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD')
CHANNELS = {
    'introductions': os.getenv('DISCORD_CHANNEL_INTRODUCTIONS'),
    'new-releases': os.getenv('DISCORD_CHANNEL_NEW_RELEASES'),
    'roles': os.getenv('DISCORD_CHANNEL_ROLES'),
    'rules': os.getenv('DISCORD_CHANNEL_RULES'),
    'welcome': os.getenv('DISCORD_CHANNEL_WELCOME')
}
COMMAND_ERRORS = [InvalidSongError, SamePlayerEliminationError]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')
    await tree.sync()
    print('Command tree synced!')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user.mentioned_in(message):
        await respond_to_ping(message)

    if message.channel_id == CHANNELS.get('new-releases'):
        store_new_release(message)

    await check_message_for_replies(message)

@client.event
async def on_member_join(member):
    await add_trainee_role(member)
    await welcome_member(member)

@tree.command(name='backfill-new-releases', description="[INTERNAL ONLY] Backfills new releases")
async def backfill(interaction):
    channel = discord.utils.get(interaction.guild.text_channels, name='new-releases')
    await backfill_releases(channel)


@tree.command(name='my-ultimate-bias', description="See who everyone's ultimate bias is!")
@discord.app_commands.describe(member='The member whose bias you want to see. " \
                               "Leave empty for your own.')
async def ultimate_bias(interaction, member: typing.Optional[str]):
    await my_ultimate_bias(interaction, member)

@tree.command(name='my-bias-group', description="See who everyone's bias group is!")
@discord.app_commands.describe(member='The member whose bias group you want to see." \
                               Leave empty for your own.')
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

client.run(TOKEN)
