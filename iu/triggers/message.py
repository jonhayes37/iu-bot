"""Parsing messages for triggers"""

import random
import re

import discord

TRIGGER_LIST = {
    '2am': [{ 'content': 'Me most nights at 2am', 'filename': 'drunk.gif' }],
    'best song': [{ 'content': "Did someone say best song? Because there's only one right answer.",
                  'filename': 'dontBelieve.gif'}],
    'clown': [{ 'filename': 'key_clown.jpg' }],
    'coin': [{ 'content': 'Heads I win, tails you lose. Deal?',
             'filename': 'coin.gif' }],
    'cream': [{ 'content': 'Sorry not sorry.',
              'filename': 'cream.gif' }],
    'ditto': [{ 'filename': 'ditto.gif' }],
    'fantastic': [{ 'filename': 'fantasticBaby.gif' }],
    'flute': [{ 'filename': 'nctSticker.gif' }],
    'genie': [{ 'content': 'Tell me your wish!',
              'filename': 'genie.gif'}],
    'in my area': [{ 'content': '<:blackpink:795873701177589761> in your area!',
                   'filename': 'blackpink.gif'}],
    'in your area': [{ 'content': '<:blackpink:795873701177589761> in your area!',
                     'filename': 'blackpink.gif'}],
    'just right': [{ 'content': 'Sorry not sorry.',
                   'filename': 'cream.gif' }],
    'jyp': [{ 'filename': 'jyp.gif' }],
    'la di da': [{ 'filename': 'la di da.gif' }],
    'ladida': [{ 'filename': 'la di da.gif' }],
    'love dive': [{ 'filename': 'dive.gif' }],
    'maniac': [{ 'filename': 'maniac.gif' }],
    'merry christmas': [{ 'filename': 'christmasEvel.gif' }],
    'mommy': [{ 'content': 'Mommy?',
              'filename': 'itzyRyujin.gif' }],
    'next level': [{ 'filename': 'nextLevel.gif'}],
    'noodles': [{ 'filename': 'jinsolRamen.gif' }],
    'pierce': [{ 'content': 'You wanna talk piercing? I can *hear* this GIF',
               'filename': 'nctSticker.gif' }],
    'piercing': [{ 'content': 'You wanna talk piercing? I can *hear* this GIF',
                 'filename': 'nctSticker.gif' }],
    'ramen': [{ 'filename': 'jinsolRamen.gif' }],
    'rough': [{ 'content': '*시간을 달려서~*',
               'filename': 'rough.gif' }],
    'ryujin': [{ 'content': 'Mommy?',
                'filename': 'itzyRyujin.gif' }],
    'rollercoaster': [{ 'filename': 'rollercoaster.gif' },
                      { 'filename': 'nmixx_rollercoaster.gif' }],
    'roller coaster': [{ 'filename': 'rollercoaster.gif' },
                       { 'filename': 'nmixx_rollercoaster.gif' }],
    'something': [{ 'content': '_나만 몰랐었던 something~_',
                  'filename': 'something.gif', 'chance': 0.25 }],
    'step it up': [{ 'filename': 'kara step.gif' }],
    'sticker': [{ 'content': "Great. Now I'm thinking about \"Sticker\" again.",
                 'filename': 'nctSticker.gif' }],
    'tipsy': [{ 'content': 'Just a bit tipsy',
               'filename': 'drunk.gif' }],
    'very nice': [{ 'content': '아주 nice!',
                   'filename': 'veryNice.gif' }],
    '아주 nice': [{ 'content': '아주 nice!',
                  'filename': 'veryNice.gif' }],
    'uhm jung hwa': [{ 'content': '엄정화 detected - paging <@330890965881585665>!' }],
    '엄정화': [{ 'content': '엄정화 detected - paging <@330890965881585665>!' }],
    'winter': [{ 'filename': 'winter.gif' }],
    'fighting': [{ 'filename': 'fighting.gif' }],
    '화이팅': [{ 'filename': 'fighting.gif' }],
    '파이팅': [{ 'filename': 'fighting.gif' }],
    'purple': [{ 'content': '보라해 :purple_heart:', 'filename': 'bts_purple.gif' },
               { 'content': "_Let's make purple~_", 'filename': 'wooah_purple.gif' }],
    'nugu mine': [{ 'content': '_Off to the mines~_', 'filename': 'nugu_mine.gif' }],
    'nugu mines': [{ 'content': '_Off to the mines~_', 'filename': 'nugu_mine.gif' }],
    'bubble': [{ 'content': '_Bubble bubble bubble!_', 'filename': 'bubble.gif' }],
    'bubbles': [{ 'content': '_Bubble bubble bubble!_', 'filename': 'bubble.gif' }],
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

def pick_trigger(trigger_key):
    triggers = TRIGGER_LIST.get(trigger_key)
    chosen_index = random.randint(0, len(triggers) - 1)
    return triggers[chosen_index]

def check_chance(cur_tr):
    chance = cur_tr.get('chance')
    if chance:
        result = random.random()
        return result < chance
    return True

def find_unique_triggers(text):
    found_triggers = [trigger for trigger in TRIGGER_LIST \
                      if trigger in text and not is_subword(text, trigger)]
    unique_filenames = set()
    unique_triggers = []
    for ft in found_triggers:
        print(f'ft: {ft}')
        cur_filenames = [opt.get('filename') for opt in TRIGGER_LIST.get(ft)]
        print(f'filenames: {cur_filenames}')
        if all([fname not in unique_filenames for fname in cur_filenames]):
            unique_triggers.append(ft)
            for fname in cur_filenames:
                unique_filenames.add(fname)
    print(f'unique triggers returning: {unique_triggers}')
    return found_triggers

async def send_messages(incoming, triggers):
    for trigger in triggers:
        chosen_trigger = pick_trigger(trigger)

        if check_chance(chosen_trigger):
            trigger_content = chosen_trigger.get('content', '')
            trigger_filename = chosen_trigger.get('filename')
            await reply_with_gif(incoming, trigger_content, trigger_filename)

async def check_message_for_replies(message):
    message_text = message.content.lower()
    found_triggers = find_unique_triggers(message_text)
    await send_messages(message, found_triggers)

async def respond_to_ping(message):
    if not message.mention_everyone:
        await reply_with_gif(message, 'IU at your service!', 'ping.gif')

def store_new_release(message, separate=False):
    """
    1. for each msg in new-releases, parse for a youtube url
    2. If the url matches, store it with the message date in a .txt file
    """
    urls = parse_message_for_youtube_url(message)
    if len(urls) > 0:
        message_datetime = message.created_at
        message_date = message_datetime.strftime('%Y-%m-%d')
        message_year = message_datetime.year

        filename = f'iu/releases/{message_year}_backfill.txt' if separate else f'iu/releases/{message_year}.txt'
        with open(filename, 'a+') as f:
            lines = list(map(lambda url: f'{message_date} // {url}\n', urls))
            f.writelines(lines)

def parse_message_for_youtube_url(msg):
    youtube_regex = r'((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(?:-nocookie)?\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|live\/|v\/)?)([\w\-]+)(\S+)?'
    matches = re.findall(youtube_regex, msg.content)
    return list(map(lambda match: ''.join(match), matches))
