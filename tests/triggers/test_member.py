"""Tests for triggers/member.py: welcoming new members."""

import pytest

from config import EMOJI_GIVE_HEART, EMOJI_HALLYU, HEART_ECONOMY_URL, ROLES_HOWTO_URL, Channel, Role
from triggers.member import add_trainee_role, welcome_member


@pytest.fixture(name="new_member")
def _new_member(make_guild, make_member):
    guild = make_guild(channels=(Channel.WELCOME, Channel.INTRODUCTIONS, Channel.ROLES, Channel.RULES,
                                 Channel.COMMUNITY), roles=(Role.TRAINEE,))
    member = make_member(user_id=42, name="Newbie")
    member.guild = guild
    return member


async def test_a_new_member_is_given_the_trainee_role(new_member):
    await add_trainee_role(new_member)

    new_member.add_roles.assert_awaited_once_with(new_member.guild.roles[0])


def _channel(member, name):
    return next(c for c in member.guild.text_channels if c.name == name)


async def test_the_welcome_is_posted_in_the_welcome_channel_with_the_wave(new_member):
    await welcome_member(new_member)

    [post] = _channel(new_member, Channel.WELCOME).sent
    assert post.kwargs["file"].filename == "iuWave.gif"
    for other in (Channel.INTRODUCTIONS, Channel.ROLES, Channel.RULES, Channel.COMMUNITY):
        assert _channel(new_member, other).sent == []


async def test_the_welcome_greets_the_member_and_points_to_each_channel(new_member):
    await welcome_member(new_member)

    text = _channel(new_member, Channel.WELCOME).sent[0].content
    assert text.startswith(f"@everyone come say hi to {new_member.mention}! They just joined the {EMOJI_HALLYU} "
                           "community.")
    assert f"rules in {_channel(new_member, Channel.RULES).mention}" in text
    assert f"in {_channel(new_member, Channel.ROLES).mention} (instructions in {ROLES_HOWTO_URL})" in text
    assert f"about yourself in {_channel(new_member, Channel.INTRODUCTIONS).mention}" in text
    assert f"heart economy ({EMOJI_GIVE_HEART}) and earning rewards for being active in {HEART_ECONOMY_URL}" in text
    assert text.endswith(f"just ask in {_channel(new_member, Channel.COMMUNITY).mention}!")
