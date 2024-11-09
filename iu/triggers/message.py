"""Parsing messages for triggers"""

import random
import re

import discord
import os

TRIGGER_LIST = {
    '2am': { 'content': 'Me most nights at 2am', 'filename': 'drunk.gif' },
    'best song': { 'content': "Did someone say best song? Because there's only one right answer.",
                  'filename': 'dontBelieve.gif'},
    'clown': { 'filename': 'key_clown.jpg' },
    'coin': { 'content': 'Heads I win, tails you lose. Deal?',
             'filename': 'coin.gif' },
    'cream': { 'content': 'Sorry not sorry.',
              'filename': 'cream.gif' },
    'ditto': { 'filename': 'ditto.gif' },
    'fantastic': { 'filename': 'fantasticBaby.gif' },
    'flute': { 'filename': 'nctSticker.gif' },
    'genie': { 'content': 'Tell me your wish!',
              'filename': 'genie.gif'},
    'in my area': { 'content': '<:blackpink:795873701177589761> in your area!',
                   'filename': 'blackpink.gif'},
    'in your area': { 'content': '<:blackpink:795873701177589761> in your area!',
                     'filename': 'blackpink.gif'},
    'just right': { 'content': 'Sorry not sorry.',
                   'filename': 'cream.gif' },
    'jyp': { 'filename': 'jyp.gif' },
    'la di da': { 'filename': 'la di da.gif' },
    'ladida': { 'filename': 'la di da.gif' },
    'love dive': { 'filename': 'dive.gif' },
    'maniac': { 'filename': 'maniac.gif' },
    'merry christmas': { 'filename': 'christmasEvel.gif' },
    'mommy': { 'content': 'Mommy?',
              'filename': 'itzyRyujin.gif' },
    'next level': { 'filename': 'nextLevel.gif'},
    'noodles': { 'filename': 'jinsolRamen.gif' },
    'pierce': { 'content': 'You wanna talk piercing? I can *hear* this GIF',
               'filename': 'nctSticker.gif' },
    'piercing': { 'content': 'You wanna talk piercing? I can *hear* this GIF',
                 'filename': 'nctSticker.gif' },
    'ramen': { 'filename': 'jinsolRamen.gif' },
    'rough': { 'content': '*시간을 달려서~*',
               'filename': 'rough.gif' },
    'ryujin': { 'content': 'Mommy?',
                'filename': 'itzyRyujin.gif' },
    'rollercoaster': { 'filename': 'rollercoaster.gif' },
    'roller coaster': { 'filename': 'rollercoaster.gif' },
    'something': { 'filename': 'something.gif', 'chance': 0.25 },
    'step it up': { 'filename': 'kara step.gif' },
    'sticker': { 'content': "Great. Now I'm thinking about \"Sticker\" again.",
                 'filename': 'nctSticker.gif' },
    'tipsy': { 'content': 'Just a bit tipsy',
               'filename': 'drunk.gif' },
    'very nice': { 'content': '아주 nice!',
                   'filename': 'veryNice.gif' },
    '아주 nice': { 'content': '아주 nice!',
                  'filename': 'veryNice.gif' },
    'uhm jung hwa': { 'content': '엄정화 detected - paging <@330890965881585665>!' },
    '엄정화': { 'content': '엄정화 detected - paging <@330890965881585665>!' },
    'winter': { 'filename': 'winter.gif' },
}

async def reply_with_gif(incoming, content, filename):
    if filename is not None:
        media_dir = 'gifs' if filename.endswith('.gif') else 'images'
        new_file = discord.File(f'iu/media/{media_dir}/{filename}', filename=filename)
        await incoming.reply(content, file=new_file)
    else:
        await incoming.reply(content)

def is_subword(text, trigger):
    splits = text.split(trigger)
    alphanum = re.compile(r'^[a-zA-Z0-9]+$')
    for i in range(len(splits) - 1):
        pre_match = len(splits[i]) != 0 and alphanum.search(splits[i][-1])
        post_match = len(splits[i+1]) != 0 and alphanum.search(splits[i+1][0])
        if not pre_match and not post_match:
            return False

    return True

def find_unique_triggers(text):
    found_triggers = [trigger for trigger in TRIGGER_LIST \
                      if trigger in text and not is_subword(text, trigger)]
    unique_triggers = set()
    found_triggers = [tr for tr in found_triggers if \
            TRIGGER_LIST.get(tr).get('filename') not in unique_triggers \
            and not unique_triggers.add(TRIGGER_LIST.get(tr).get('filename'))]

    def check_chance(trigger):
        cur_tr = TRIGGER_LIST.get(trigger)
        chance = cur_tr.get('chance')
        if chance:
            result = random.random()
            return result < chance
        return True

    return list(filter(check_chance, found_triggers))

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
    if not message.mention_everyone:
        await reply_with_gif(message, 'IU at your service!', 'ping.gif')

def store_new_release(message):
    """
    1. for each msg in new-releases, parse for a youtube url
    2. If the url matches, store it with the message date in a .txt file
    """
    urls = parse_message_for_youtube_url(message)
    if len(urls) > 0:
        message_datetime = message.created_at
        message_date = message_datetime.strftime('%Y-%m-%d')
        message_year = message_datetime.year

        with open(f'iu/releases/{message_year}.txt', 'a+') as f:
            lines = list(map(lambda url: f'{message_date} // {url}\n', urls))
            f.writelines(lines)

def parse_message_for_youtube_url(msg):
    youtube_regex = r'^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(?:-nocookie)?\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|live\/|v\/)?)([\w\-]+)(\S+)?$'
    matches = re.findall(youtube_regex, msg.content)
    return list(map(lambda match: ''.join(match), matches))