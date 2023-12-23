"""Unit testing for calendar.py"""

import discord
import pytest
from commands.calendar import CALENDAR_LINK, send_calendar
from testing.interaction import MockInteraction


@pytest.mark.asyncio()
async def test_send_calendar():
    interaction = MockInteraction()
    expected_message = "Here's the <:hallyu:795848873910206544> calendar with all of our " \
        f"events! {CALENDAR_LINK}\nHow to add to your calendar:"
    expected_file = discord.File('iu/media/gifs/calendar_tutorial.gif',
                                 filename='calendar_tutorial.gif')

    await send_calendar(interaction)

    interaction.assert_message_equals(expected_message)
    interaction.assert_file_equals(expected_file)
