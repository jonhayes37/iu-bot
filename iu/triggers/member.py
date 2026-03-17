"""
member.py contains the logic for Discord member-based triggers.
"""

import discord


async def add_trainee_role(member):
    trainee_role = discord.utils.get(member.guild.roles, name='Trainee')
    await member.add_roles(trainee_role)

async def welcome_member(member):
    welcome_channel = discord.utils.get(member.guild.text_channels, name='welcome')
    intro_channel = discord.utils.get(member.guild.text_channels, name='introductions')
    roles_channel = discord.utils.get(member.guild.text_channels, name='roles')
    rules_channel = discord.utils.get(member.guild.text_channels, name='rules')
    community_channel = discord.utils.get(member.guild.text_channels, name='community')

    message = f'@everyone come say hi to {member.mention}! They just joined the ' \
        f'<:hallyu:795848873910206544> community. {member.mention}, to get started you can:\n' \
        f"- Check out our community's rules in {rules_channel.mention}\n" \
        f"- Add roles to rep your biases and be notified about watch parties and events in {roles_channel.mention} " \
        "(instructions in https://discord.com/channels/795846406187384842/838498988566642708/1066953623667482665)\n" \
        f"- If you're comfortable, share a bit about yourself in {intro_channel.mention}\n" \
        f"- Learn about the heart economy (<a:aGiveHeart:1472262590477500569>) and earning rewards for being " \
        f"active in https://discord.com/channels/795846406187384842/795855921020010496/1472346872147476551\n\n" \
        f"Most importantly, have fun and if you have any questions just ask in {community_channel.mention}!"

    wave_file = discord.File('iu/media/gifs/iuWave.gif', filename='iuWave.gif')
    await welcome_channel.send(message, file=wave_file)
