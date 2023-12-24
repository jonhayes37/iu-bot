"""Unit testing for member.py"""

import discord
import pytest
from testing.interaction import MockUser
from triggers.member import add_trainee_role, welcome_member


@pytest.mark.asyncio()
async def test_add_trainee_role():
    user = MockUser(name="HallyU")

    await add_trainee_role(user)

    user.assert_has_role("Trainee")

@pytest.mark.asyncio()
async def test_welcome_member():
    user = MockUser(name="HallyU")
    expected_message = '@everyone come say hi to HallyU! They just joined the ' \
        '<:hallyu:795848873910206544> community. HallyU, be sure to check the ' \
        '<@!rules> channel to get started, then head over to ' \
        '<@!roles> to get roles for your favourite fandoms! Feel free to share ' \
        'a bit about yourself in <@!introductions> too.'
    expected_file = discord.File('iu/media/gifs/iuWave.gif', filename='iuWave.gif')

    await welcome_member(user)

    welcome_channel = user.guild.text_channels[0]
    welcome_channel.assert_message_equals(expected_message)
    welcome_channel.assert_file_equals(expected_file)
