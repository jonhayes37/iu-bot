import discord

TRAINEE_ROLE=986783552270114866

async def add_trainee_role(member):
    trainee_role = discord.utils.get(member.guild.roles, name='Trainee')
    await member.add_roles(trainee_role)

async def welcome_member(member):
    welcome_channel = discord.utils.get(member.guild.text_channels, name='welcome')
    intro_channel = discord.utils.get(member.guild.text_channels, name='introductions')
    roles_channel = discord.utils.get(member.guild.text_channels, name='roles')
    rules_channel = discord.utils.get(member.guild.text_channels, name='rules')

    message = f'@everyone come say hi to {member.mention}! They just joined the <:hallyu:795848873910206544> community. ' \
        f'{member.mention}, be sure to check the {rules_channel.mention} channel to get started, then head over to ' \
        f'{roles_channel.mention} to get roles for your favourite fandoms! Feel free to share a bit about yourself ' \
        f'in {intro_channel.mention} too.'
    wave_file = discord.File('media/gifs/iuWave.gif', filename='iuWave.gif')
    await welcome_channel.send(message, file=wave_file)
