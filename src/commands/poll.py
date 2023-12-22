NUMBER_EMOJI_NAMES = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']
NUMBER_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]

async def generate_poll(interaction, question, answers):
    message_chunks = [f'{interaction.user.mention} asks: {question}\n']
    possible_answers = answers.split('|')
    if len(possible_answers) > 9:
        await interaction.response.send_message(f"Sorry {interaction.user.mention}, a maximum of 9 answers are supported per poll! You provided {len(possible_answers)}.")
        return

    for index, answer in enumerate(possible_answers):
        message_chunks.append(f':{NUMBER_EMOJI_NAMES[index]}: {answer.strip()}')
    message = '\n'.join(message_chunks)
    await interaction.response.send_message(message)
    
    sent_message = await interaction.original_response()
    await add_voting_options(sent_message, len(possible_answers))

async def add_voting_options(message, num_answers):
    for i in range(num_answers):
        await message.add_reaction(NUMBER_EMOJI[i])