"""
Unit testing for message.py.
"""
import discord
import unittest
import pytest
from testing.interaction import MockMessage
from parameterized import parameterized
from triggers.message import check_message_for_replies, is_subword, respond_to_ping


class TestIsSubword(unittest.TestCase):
    """Unit testing for is_subword."""

    @parameterized.expand([
        ('this is a message with best song in it', 'best song', False),
        ('flute', 'flute', False),
        ('"flute?"', 'flute', False),
        ('through', 'rough', True)
    ])
    def test_is_subword(self, text, trigger, expected):
        self.assertEqual(is_subword(text, trigger), expected)

@pytest.mark.asyncio()
@pytest.mark.parametrize(["mention_everyone", "expected_message", "expected_file"],
[
    # Message tags everyone, don't respond
    (True, None, None),
    # Normal message, respond
    (False,
     'IU at your service!',
     discord.File("iu/media/gifs/ping.gif", filename='ping.gif')),
])
async def test_add_trainee_role(mention_everyone, expected_message, expected_file):
    message = MockMessage("@IU I love you!", mention_everyone)

    await respond_to_ping(message)

    message.assert_reply_message_equals(expected_message)
    message.assert_reply_file_equals(expected_file)

@pytest.mark.asyncio()
async def test_check_message_for_replies():
    message = MockMessage("Well LA DI DA, look at the time! It's 2am! uhm jung hwa is here.")
    la_di_da_file = discord.File('iu/media/gifs/la di da.gif', filename='la di da.gif')
    am_file = discord.File('iu/media/gifs/drunk.gif', filename='drunk.gif')

    await check_message_for_replies(message)

    assert len(message.responses) == 3

    # La di da reply
    message.assert_reply_message_equals('')
    message.assert_reply_file_equals(la_di_da_file)

    # 2am reply
    message.assert_reply_message_equals('Me most nights at 2am')
    message.assert_reply_file_equals(am_file)

    # Uhm Jung Hwa reply
    message.assert_reply_message_equals('엄정화 detected - paging <@330890965881585665>!')