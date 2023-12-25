"""/rankdown-turn command"""

from discord import app_commands

TURN_ORDER = [
    "904751089633615972", # HallyU
    "227092770110570496", # ChrisPrime
    "819331800366841856", # Feldarak
    "202927629018333184", # Kpopbrandy
    "149935440042917888", # Frozen Light
    "109190347854217216", # Helen
    "317621715247300609", # Stromsolar
    "797897851907866665", # Diana4Dragons
    "271060400886251530", # Xion Rin
]

class NoPreviousTurnException(Exception):
    """Custom exception for no previous turn existing."""
    def __init__(self):
        self.message = "No previous turn was found! The command only supports turns after the first round."
        super().__init__(self.message)

class ReasonTooLongError(app_commands.AppCommandError):
    """Custom command error for a reason that's too long for the Discord API"""
    def __init__(self):
        self.message = "Your reasoning is too long! The elimination and nomination reasons " \
                        "should each be less than 2,000 characters."
        super().__init__(self.message)

class InvalidSongError(app_commands.AppCommandError):
    """Custom command error for a song that's not in the In Danger list"""
    def __init__(self, song):
        self.message = f"\"{song}\" was not found in the In Danger list! Make sure you copy " \
                        "the song exactly as it appears in the In Danger list."
        super().__init__(self.message)

class SamePlayerEliminationError(app_commands.AppCommandError):
    """Custom command error for a player eliminating a song they nominated"""
    def __init__(self, song):
        self.message = f"You nominated \"{song}\", so you cannot eliminate it!"
        super().__init__(self.message)

async def handle_command_error(error, interaction):
    await interaction.response.send_message(error.message, ephemeral=True)

async def get_previous_turn(channel):
    message_history = await channel.history(limit=10)
    for message in message_history:
        if "**in danger**" in message.content.lower():
            return message.content

    raise NoPreviousTurnException

def parse_danger_list(turn_message):
    danger_songs = []
    message_lines = turn_message.split('\n')
    in_danger_index = message_lines.index("**In Danger**")
    for line in message_lines[in_danger_index + 1:]:
        if line:
            danger_songs.append(line)
        else:
            break
    return danger_songs

async def update_danger_list(channel, elim, nom, username):
    previous_message = await get_previous_turn(channel)
    songs = parse_danger_list(previous_message)
    def strip_person(line):
        song_pieces = line.split(' (')
        return ' ('.join(song_pieces[:len(song_pieces) - 1])

    clean_songs = list(map(strip_person, songs))
    strip_songs = list(map(str.strip, clean_songs))
    lower_songs = list(map(str.lower, strip_songs))

    try:
        elim_index = lower_songs.index(elim.lower())
    except ValueError as exc:
        raise InvalidSongError(elim) from exc

    if username.lower() in songs[elim_index].lower():
        raise SamePlayerEliminationError(elim)

    songs.pop(elim_index)
    songs.append(f'{nom} ({username})')
    return songs

def get_next_player(cur_player):
    cur_player_index = TURN_ORDER.index(str(cur_player))
    next_index = (cur_player_index + 1) % len(TURN_ORDER)
    return TURN_ORDER[next_index]

def split_turn_message(message):
    messages = []
    message_lines = message.split('\n')
    in_danger_index = message_lines.index("**In Danger**")

    elim_nom_message = '\n'.join(message_lines[:in_danger_index])
    if len(elim_nom_message) > 2000:
        for index, line in enumerate(message_lines[:in_danger_index]):
            if "i nominate" in line.lower():
                elim_message = '\n'.join(message_lines[:index])
                nom_message = '\n'.join(message_lines[index:in_danger_index])
                if len(elim_message) > 2000 or len(nom_message) > 2000:
                    raise ReasonTooLongError
                messages += [elim_message, nom_message]
    else:
        messages.append(elim_nom_message)

    messages.append('\n'.join(message_lines[in_danger_index:]))
    return messages

async def rankdown_turn(interaction, elim, elim_reason, nom, nom_reason,
                        next_message = "your turn!"):
    try:
        cur_player_id = interaction.user.id
        username = interaction.user.nick if interaction.user.nick else \
            interaction.user.display_name if interaction.user.display_name else \
            interaction.user.global_name
        next_player = get_next_player(cur_player_id)

        updated_danger_songs = await update_danger_list(interaction.channel, elim, nom, username)
        danger_list_str = '\n'.join(updated_danger_songs)

        message_content = f"""<@{cur_player_id}>'s turn:

I eliminate **{elim}**. {elim_reason}

I nominate **{nom}**. {nom_reason}

**In Danger**
{danger_list_str}

<@{next_player}> {next_message}"""
        if len(message_content) >= 2000:
            messages = split_turn_message(message_content)
            await interaction.response.send_message(messages[0])
            for message in messages[1:]:
                await interaction.channel.send(message)
        else:
            await interaction.response.send_message(message_content)
    except (InvalidSongError, SamePlayerEliminationError, ReasonTooLongError, NoPreviousTurnException) as ex:
        await handle_command_error(ex, interaction)
