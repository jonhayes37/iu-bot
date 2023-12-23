"""Unit testing for poll.py"""

import pytest
from commands.poll import generate_poll
from testing.interaction import MockInteraction

@pytest.mark.asyncio()
@pytest.mark.parametrize(["answers", "expected_message"],
                         [
    ("Yes|No", """HallyU asks: Is IU the best?

:one: Yes
:two: No"""),
    ("1|2|3|4|5|6|7|8|9|10",
     "Sorry HallyU, a maximum of 9 answers are supported per poll! You provided 10.")
])
async def test_poll(answers, expected_message):
    interaction = MockInteraction("HallyU")
    question = "Is IU the best?"

    await generate_poll(interaction, question, answers)

    interaction.assert_message_equals(expected_message)
