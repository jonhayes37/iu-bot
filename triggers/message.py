"""Parsing messages for triggers"""

import re

import discord

TRIGGER_LIST = {
    'magicmagic': { 'content': 'Wow it worked!', 'filename': 'test.gif' },
    # '2am': { 'content': 'Me most nights at 2am', 'filename': 'drunk.gif' },
    # 'best song': { 'content': "Did someone say best song? Because there's only one right answer.", 'filename': 'dontBelieve.gif'},
    # 'clown': { 'filename': 'key_clown.jpg' },
    # 'coin': { 'content': 'Heads I win, tails you lose. Deal?', 'filename': 'coin.gif' },
    # 'cream': { 'content': 'Sorry not sorry.', 'filename': 'cream.gif' },
    # 'ditto': { 'filename': 'ditto.gif' },
    # 'flute': { 'filename': 'nctSticker.gif' },
    # 'genie': { 'content': 'Tell me your wish!', 'filename': 'genie.gif'},
    # 'in my area': { 'content': '<:blackpink:795873701177589761> in your area!', 'filename': 'blackpink.gif'},
    # 'in your area': { 'content': '<:blackpink:795873701177589761> in your area!', 'filename': 'blackpink.gif'},
    # 'just right': { 'content': 'Sorry not sorry.', 'filename': 'cream.gif' },
    # 'jyp': { 'filename': 'jyp.gif' },
    # 'la di da': { 'filename': 'la di da.gif' },
    # 'ladida': { 'filename': 'la di da.gif' },
    # 'love dive': { 'filename': 'dive.gif' },
    # 'maniac': { 'filename': 'maniac.gif' },
    # 'merry christmas': { 'filename': 'christmasEvel.gif' },
    # 'mommy': { 'content': 'Mommy?', 'filename': 'itzyRyujin.gif' },
    # 'next level': { 'filename': 'nextLevel.gif'},
    # 'noodles': { 'filename': 'jinsolRamen.gif' },
    # 'pierce': { 'content': 'You wanna talk piercing? I can *hear* this GIF', 'filename': 'nctSticker.gif' },
    # 'piercing': { 'content': 'You wanna talk piercing? I can *hear* this GIF', 'filename': 'nctSticker.gif' },
    # 'ramen': { 'filename': 'jinsolRamen.gif' },
    # 'rough': { 'content': '*시간을 달려서~*', 'filename': 'rough.gif' },
    # 'ryujin': { 'content': 'Mommy?', 'filename': 'itzyRyujin.gif' },
    # 'rollercoaster': { 'filename': 'rollercoaster.gif' },
    # 'roller coaster': { 'filename': 'rollercoaster.gif' },
    # 'step it up': { 'filename': 'kara step.gif' },
    # 'sticker': { 'content': "Great. Now I'm thinking about \"Sticker\" again.", 'filename': 'nctSticker.gif' },
    # 'tipsy': { 'content': 'Just a bit tipsy', 'filename': 'drunk.gif' },
    # 'very nice': { 'content': '아주 nice!', 'filename': 'veryNice.gif' }
}


async def reply_with_gif(incoming, content, filename):
    media_dir = 'gifs' if filename.endswith('.gif') else 'images'
    new_file = discord.File(f'media/{media_dir}/{filename}', filename=filename)
    await incoming.reply(content, file=new_file)


def is_subword(text, trigger):
    splits = text.split(trigger)
    alphanum = re.compile(r'/^[a-zA-Z0-9]+$/')
    for i in range(len(splits)):
        pre_match = len(splits[i]) != 0 and re.search(alphanum, splits[i][-1])
        post_match = len(splits[i+1]) != 0 and re.search(alphanum, splits[i+1][0])
        if not pre_match and not post_match:
            return False

    return True


def find_unique_triggers(text):
    found_triggers = [trigger for trigger in TRIGGER_LIST if trigger in text and not is_subword(text, trigger)]
    unique_triggers = set()
    return [tr for tr in found_triggers if \
            TRIGGER_LIST.get(tr).get('filename') not in unique_triggers \
            and not unique_triggers.add(TRIGGER_LIST.get(tr).get('filename'))]


async def send_messages(incoming, triggers):
    for trigger in triggers:
        trigger_info = TRIGGER_LIST.get(trigger)
        trigger_content = trigger_info.get('content', '')
        trigger_filename = trigger_info.get('filename')
        await reply_with_gif(incoming, trigger_content, trigger_filename)


async def check_message_for_replies(message):
    message_text = message.content.lower()
    found_triggers = find_unique_triggers(message_text)
    await send_messages(message, found_triggers)


async def respond_to_ping(message):
    await reply_with_gif(message, 'IU at your service!', 'ping.gif')