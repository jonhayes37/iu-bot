"""
member.py contains the logic for Discord member-based triggers.
"""

import discord
from config import Channel, EMOJI_GIVE_HEART, EMOJI_HALLYU, HEART_ECONOMY_URL, MEDIA_DIR, ROLES_HOWTO_URL, Role


async def add_trainee_role(member):
    trainee_role = discord.utils.get(member.guild.roles, name=Role.TRAINEE)
    await member.add_roles(trainee_role)

async def welcome_member(member):
    welcome_channel = discord.utils.get(member.guild.text_channels, name=Channel.WELCOME)
    intro_channel = discord.utils.get(member.guild.text_channels, name=Channel.INTRODUCTIONS)
    roles_channel = discord.utils.get(member.guild.text_channels, name=Channel.ROLES)
    rules_channel = discord.utils.get(member.guild.text_channels, name=Channel.RULES)
    community_channel = discord.utils.get(member.guild.text_channels, name=Channel.COMMUNITY)

    message = f'@everyone come say hi to {member.mention}! They just joined the ' \
        f'{EMOJI_HALLYU} community. {member.mention}, to get started you can:\n' \
        f"- Check out our community's rules in {rules_channel.mention}\n" \
        f"- Add roles to rep your biases and be notified about watch parties and events in {roles_channel.mention} " \
        f"(instructions in {ROLES_HOWTO_URL})\n" \
        f"- If you're comfortable, share a bit about yourself in {intro_channel.mention}\n" \
        f"- Learn about the heart economy ({EMOJI_GIVE_HEART}) and earning rewards for being " \
        f"active in {HEART_ECONOMY_URL}\n\n" \
        f"Most importantly, have fun and if you have any questions just ask in {community_channel.mention}!"

    wave_file = discord.File(MEDIA_DIR / 'gifs' / 'iuWave.gif', filename='iuWave.gif')
    await welcome_channel.send(message, file=wave_file)
