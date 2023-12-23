"""HMA pick commands"""

import os


def filepath_for_user(user_id):
    return f'iu/hmas/{user_id}.txt'

async def add_hma_pick(interaction, pick):
    user_id = interaction.user.id
    file_path = filepath_for_user(user_id)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'a+', encoding="utf-8") as file:
        file.write(pick + '\n')

    response_message = 'Your pick has been saved! You can check all of your picks by using ' \
        '`/my-hma-picks` or delete them with `/delete-hma-picks`.'
    await interaction.response.send_message(response_message, ephemeral=True)

async def my_hma_picks(interaction):
    user_id = interaction.user.id
    lines = []
    file_path = filepath_for_user(user_id)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding="utf-8") as file:
            lines = [f'- {line}' for line in file.readlines()]

    has_picks = len(lines) > 0
    message = 'Here are your HMA picks!\n' + ''.join(lines)
    response_message = "Check your DMs! I've sent your HMA picks there." if has_picks else \
    "You don't have any saved HMA picks yet! Add one by using `/add-hma-pick`."

    await interaction.response.send_message(response_message, ephemeral=True)
    if has_picks:
        await interaction.user.send(message)

async def delete_hma_picks(interaction):
    user_id = interaction.user.id
    file_path = filepath_for_user(user_id)
    if os.path.exists(file_path):
        os.remove(file_path)

    response_message = 'Your HMA picks have been deleted. You can add new a new pick by using ' \
                       '`/add-hma-pick`.'
    await interaction.response.send_message(response_message, ephemeral=True)
