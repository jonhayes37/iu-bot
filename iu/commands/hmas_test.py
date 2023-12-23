"""Unit testing for bias_group.py"""

import os

import pytest
from commands.hmas import add_hma_pick, delete_hma_picks, my_hma_picks
from testing.interaction import MockInteraction, MockUser

TEST_USER = MockUser(user_id="test123")
TEST_PICK = "IU is the best female soloist"

def cleanup():
    if os.path.exists('iu/hmas/test123.txt'):
        os.remove('iu/hmas/test123.txt')

@pytest.mark.asyncio()
async def test_add_hma_pick():
    interaction = MockInteraction(TEST_USER)
    expected_message = 'Your pick has been saved! You can check all of your picks by using ' \
        '`/my-hma-picks` or delete them with `/delete-hma-picks`.'

    await add_hma_pick(interaction, TEST_PICK)

    interaction.assert_message_equals(expected_message, ephemeral=True)
    cleanup()

@pytest.mark.asyncio()
async def test_delete_hma_picks():
    interaction = MockInteraction(TEST_USER)
    expected_message = 'Your HMA picks have been deleted. You can add new a new pick by using ' \
                       '`/add-hma-pick`.'

    await add_hma_pick(interaction, TEST_PICK)
    await delete_hma_picks(interaction)

    interaction.assert_message_equals(expected_message, ephemeral=True)

    new_interaction = MockInteraction(TEST_USER)
    await my_hma_picks(new_interaction)
    new_interaction.assert_message_equals(
        "You don't have any saved HMA picks yet! Add one by using `/add-hma-pick`.",
        ephemeral=True)
    cleanup()

@pytest.mark.asyncio()
async def test_my_hma_picks():
    interaction = MockInteraction(TEST_USER)
    expected_message = "Check your DMs! I've sent your HMA picks there."
    expected_dm = f'Here are your HMA picks!\n- {TEST_PICK}'

    await delete_hma_picks(interaction)
    await add_hma_pick(interaction, TEST_PICK)

    new_interaction = MockInteraction(TEST_USER)
    await my_hma_picks(new_interaction)

    new_interaction.assert_message_equals(expected_message, ephemeral=True)
    new_interaction.user.assert_dm_equals(expected_dm)
    cleanup()
