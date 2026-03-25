"""Commands for bias embeds"""
import typing

import discord

USERNAMES = {
  "Alexrandia": "453573453623328778",
  "Cai": "330890965881585665",
  "Cats & Kpop": "758818887672004609",
  "Chris Prime!": "227092770110570496",
  "Diana4Dragons": "797897851907866665",
  "DoctorQuackerzzz": "600309699186917397",
  "HallyU": "904751089633615972",
  "InsomniAloha": "521827421968924672",
  "Stromsolar": "317621715247300609",
  "Kpopbrandy": "202927629018333184",
  "Xion Rin": "271060400886251530",
  "Volt D. Resin": "520406649970884632",
}

ARTIST_BIAS_MAP = {
  USERNAMES["HallyU"]: {
    'album': "[Girls & Peace](https://youtu.be/xVYXTEG0Qeg)",
    'bias': "Seohyun",
    'b_track': "[Lucky Like That](https://youtu.be/THDVlS51ywI)",
    'debut_date': "August 5, 2007",
    'embed_colour': 0xff4980,
    'filename': "snsd.jpg",
    'label': "SM Entertainment",
    'members': "Hyoyeon, Seohyun, Sooyoung, Sunny, Taeyeon, Tiffany, Yoona, Yuri",
    'name': "Girls' Generation (소녀시대)",
    'reason': '\n'.join([
      "The Nation's Girl Group! These girls and their body of work speaks for itself. " \
      "Nobody did it like them.",
      "*Right now, Girls' Generation*",
      "*From now on, Girls' Generation*",
      "*Forever, Girls' Generation*",
      "<:snsd:795873457086791741>"
    ]),
    'title_track': "[Into The New World (다시 만난 세계)](https://youtu.be/0k2Zzkw_-0I)",
  },
  USERNAMES["Chris Prime!"]: {
    'album': "[Time For Us](https://youtu.be/i6rIeFM9kfo)",
    'bias': "Yuju (she's so weird, yet graceful and elegant and is an absolutely " \
            "top tier vocalist)",
    'b_track': "[You Are My Star](https://youtu.be/3EKLdmyPyVs), " \
               "[Wheel of the Year](https://youtu.be/tiiu8LhmHcE)",
    'debut_date': "January 15, 2015",
    'embed_colour': 0x00b2ca,
    'filename': "gfriend.jpg",
    'label': "Source Music",
    'members': "Eunha, SinB, Sowon, Umji, Yerin, Yuju",
    'name': "GFriend (여자친구)",
    'reason': '\n'.join([
      "There's something so special about them as a group. They're one of a very few K-pop " \
      "groups that MADE trends rather than chasing them, they have one of the most solid and " \
      "expansive discographies in K-pop, the well-earned title of Queens of Synchronization, " \
      "and they have the respect of just about everybody in the industry. I might not Stan " \
      "them as hard as I used to since their disbandment, but in my heart they'll always be " \
      "number 1.",
    ]),
    'title_track': "[Mago](https://youtu.be/LmBYPXGqtss), [Rainbow](https://youtu.be/ZSXN_dpG5jk)",
  },
  USERNAMES["Diana4Dragons"]: {
    'album': "[Love Yourself Answer](https://youtu.be/A65TAHQqU6I)",
    'bias': "Jin",
    'b_track': "[Answer: Love Myself](https://youtu.be/9mwRYgMmSGE), " \
               "[Moon](https://youtu.be/F5H3g0UR7CI)",
    'debut_date': "June 12, 2013",
    'embed_colour': 0x69448e,
    'filename': "bts.jpg",
    'label': "Big Hit Music",
    'members': "J-Hope, Jimin, Jin, Jungkook, RM, Suga, V",
    'name': "BTS (방탄소년단)",
    'reason': '\n'.join([
      "BTS is the group that first made me interested in and care about the members as people " \
      "and not just the music. They are the only group where all of the members are high on " \
      "my bias list. I love a lot of their discography to the point that answering about my " \
      "favourites was a process that took days - and there are still two b-sides.",
      "<:bts:800437846367928341>"
    ]),
    'title_track': "[Blood Sweat & Tears](https://youtu.be/hmE9f-TEutc)",
  },
  USERNAMES["Xion Rin"]: {
    'album': "[Schxxl Out](https://youtu.be/7CyKSvPd2mA)",
    'bias': "Nayoung & Xiyeon",
    'b_track': "[Rollercoaster](https://youtu.be/zQuLvMialKU)",
    'debut_date': "March 21, 2017",
    'embed_colour': 0xf88378,
    'filename': "pristin.jpg",
    'label': "Pledis Entertainment",
    'members': "Eunwoo, Kyla, Kyulkyung, Nayoung, Rena, Roa, Sungyeon, Xiyeon, Yehana, Yuha",
    'name': "Pristin (프리스틴)",
    'reason': '\n'.join([
      "Pristin was the first group I was truly, 100% invested in when it came to Kpop. Their " \
      "level of talent, their personalities and how clearly they all loved each other just " \
      "stole my heart and even though they weren't together long, you can tell these girls " \
      "still love each other so much.",
      "<:pristin:838245257447604255>"
    ]),
    'title_track': "[We Like](https://youtu.be/J6LAzgZi8N8)",
  },
  USERNAMES["Alexrandia"]: {
    'album': "[Siren: Dawn](https://youtu.be/DVDMq5q8SzE)",
    'bias': "OT5! (Every member constantly wrecks me, so I gave in to them all.)",
    'b_track': "[Clover](https://youtu.be/-UgUWK6GLic), " \
               "[Chasing Love](https://youtu.be/3cGmnsAWinU)",
    'debut_date': "May 23, 2017",
    'embed_colour': 0x23a55a,
    'filename': "ace.jpg",
    'label': "Beat Interactive",
    'members': "Byeongkwan, Chan, Donghun, Jun, Wow",
    'name': "A.C.E (에이스)",
    'reason': '\n'.join([
      "I never fan-girled in my life before I found A.C.E, but they deserve it in so many ways. " \
      "Their talent, their aesthetic, their personalities, and their open support for the " \
      "LGBTQ+ community. They can pull off any concept and have a song for every mood.",
      "<:ace:837490788216078356>"
    ]),
    'title_track': "[Under Cover](https://youtu.be/qODWFe6v3zA)",
  },
  USERNAMES["Kpopbrandy"]: {
    'album': "[The Billage of Perception: Chapter One](https://youtu.be/sk8zp9xiRoA)",
    'bias': "Siyoon",
    'b_track': "[The Eleventh Day](https://youtu.be/iVprptQ7ZMM)",
    'debut_date': "November 10, 2021",
    'embed_colour': 0x98b6e4,
    'filename': "billlie.jpeg",
    'label': "Mystic Story",
    'members': "Haram, Haruna, Moon Sua, Sheon, Siyoon, Suhyeon, Tsuki",
    'name': "Billlie (빌리)",
    'reason': '\n'.join([
      "I found Billlie through Sheon and GP999. Knowing she was going to join them initially " \
      "got me interested but this group is so magnetic once I fell for them I knew I would be " \
      "in it for life.  The music is absolutely Mystical! (Yes that is a play on them being in " \
      "Mystic Story!)",
      "<:billlie:915261590452985946>"
    ]),
    'title_track': "[RING x RING](https://youtu.be/i9jhxOwcaw0)",
  },
  USERNAMES["Stromsolar"]: {
    'album': "[I Trust](https://youtu.be/FxrAXYOpF0k)",
    'bias': "Minnie",
    'b_track': "[Villain Dies](https://youtu.be/jYkvghyX_mo)",
    'debut_date': "May 2, 2018",
    'embed_colour': 0xe11900,
    'filename': "gidle.jpg",
    'label': "Cube Entertainment",
    'members': "Minnie, Miyeon, Shuhua, Soojin, Soyeon, Yuqi",
    'name': "(G)I-DLE ((여자)아이들)",
    'reason': '\n'.join([
      "<:gidle:795876356491575318> is the group that got me into Kpop. I like the fact that " \
      "this is a self product group. I love their concept that consist in creating a unique " \
      "group by having members with very different charms/abilities and by fully using those " \
      "abilities in every single song. They are always able to create songs with new and " \
      "original concepts while having a distinctive style."
    ]),
    'title_track': "[Lion](https://youtu.be/6oanIo_2Z4Q)",
  },
  USERNAMES["Cats & Kpop"]: {
    'album': "[The Perfect Red Velvet](https://youtu.be/804vjsGeags)",
    'bias': "Seulgi",
    'b_track': "They're the B-Side Queens, so this is always in flux!",
    'debut_date': "August 1, 2014",
    'embed_colour': 0xfda487,
    'filename': "red_velvet.jpeg",
    'label': "SM Entertainment",
    'members': "Irene, Joy, Seulgi, Wendy, Yeri",
    'name': "Red Velvet (레드벨벳)",
    'reason': '\n'.join([
      "I chose <:redvelvet:795873702054330408> as my bias group due to their genre versatility " \
      "and impeccable discography."
    ]),
    'title_track': "[Psycho](https://youtu.be/uR8Mrt1IpXg)",
  },
  USERNAMES["InsomniAloha"]: {
    'album': "[Dystopia: The Tree of Language](https://youtu.be/9wA7acMsbw4)",
    'bias': "JiU (Kim Minji)",
    'b_track': "[Trap](https://youtu.be/H9AYF1Sl72Q)",
    'debut_date': "January 13, 2017",
    'embed_colour': 0x8a3324,
    'filename': "dreamcatcher.png",
    'label': "Happyface Entertainment",
    'members': "Dami, Gahyeon, Handong, JiU, Siyeon, SuA, Yoohyeon",
    'name': "Dreamcatcher (드림캐쳐)",
    'reason': '\n'.join([
      "I love their unique music and sound. Their choreography is always top notch and their " \
      "live vocals are amazing. Besides being amazing artists they seem to very genuine and " \
      "down to earth people. When they are off stage it's always fun to watch their antics."
    ]),
    'title_track': "[Piri](https://youtu.be/Pq_mbTSR-a0)",
  },
  USERNAMES["Cai"]: {
    'album': "[Prima Donna](https://youtu.be/1tiAOQkMrXw)",
    'bias': "Eunji",
    'b_track': "[Miss Agent](https://youtu.be/T2-0at7naVo)",
    'debut_date': "August 12, 2010",
    'embed_colour': 0x732788,
    'filename': "9muses.jpeg",
    'label': "Star Empire",
    'members': "Bini, Euaerin, Eunji, Hyemi, Hyuna, Jaekyung, Keumjo, Kyungri, LeeSem, Minha, " \
               "Rana, Sera, Sojin, Sungah",
    'name': "9Muses (나인뮤지스)",
    'reason': '\n'.join([
      "9Muses had so many lineup changes it can't really be thought of as one group, but over " \
      "time I grew to love all of them. They're the group that taught me how to be a Kpop fan " \
      "from enjoying aegyo to coming to terms with how the end product that is Kpop is made. " \
      "As a group, 9Muses is painfully flawed in shockingly well documented ways that can't be " \
      "denied. As an idea, however, 9Muses understood the assignment and consistently provided " \
      "my favorite kind of concept: The mature sexy concept. In that way, they were brilliant."
    ]),
    'title_track': "[Wild](https://youtu.be/fwN_Axs7pL4)",
  },
  USERNAMES["DoctorQuackerzzz"]: {
    'album': "[Joy](https://youtu.be/mtc0-ujaqO0)",
    'bias': "Wooyeon (우연)",
    'b_track': "[Straight Up](https://youtu.be/70WY66piv20)",
    'debut_date': "May 15, 2020",
    'embed_colour': 0xc598ed,
    'filename': "wooah.png",
    'label': "H Music Entertainment",
    'members': "Lucy, Minseo, Nana, Sora, Wooyeon",
    'name': "woo!ah! (우아)",
    'reason': '\n'.join([
      "Time and time again, woo!ah! had piqued my curiosity till the eventual time of Queendom " \
      "Puzzle, where both Nana and Wooyeon participated. With time, research, and my love " \
      "for them growing, they rose to the top, claiming my ult group spot, and a dear near " \
      "place to my heart, even if I was a newbie Wow. They were even one of the first ever " \
      "groups I hosted for in doing Group Orders, in which I am glad to have chosen them as " \
      "my first group to host for."
    ]),
    'title_track': "[Blush](https://youtu.be/yh5W41ANcjo)",
  }
}

ULTIMATE_BIAS_MAP = {
  USERNAMES['HallyU']: {
    'birth_name': "Seo Juhyun (서주현)",
    'birthday': "June 28, 1991",
    'embed_colour': 0xff4980,
    'filename': "seohyun.jpg",
    'group': "Girls' Generation (소녀시대)",
    'hometown': "Seoul, South Korea",
    'name': "Seohyun (서현)",
    'position': "Maknae, Lead Vocalist",
    'reason': "She was my first bias, and the start of it all! A talented musician, angelic " \
    "vocalist, stunning visual and hilarious troublemaker <:snsd:795873457086791741>"
  },
  USERNAMES['Chris Prime!']: {
    'birth_name': "Son Seung Wan (손승완)",
    'birthday': "February 21, 1994",
    'embed_colour': 0x0070b8,
    'filename': "wendy.jpg",
    'group': "Red Velvet (레드벨벳)",
    'hometown': "Seoul, South Korea",
    'name': "Wendy (웬디)",
    'position': "Main Vocalist",
    'reason': "I keep going back to the emptiness I felt during the year of hell when Wendy was " \
    "absent from activities due to injuries, and how I felt the first time she returned to " \
    "perform live again with the rest of the 'group'. It was a feeling of indescribable and " \
    "unrestrained bliss. She's not only one of if not the best third gen main vocal, but she " \
    "continues to be a positive influence and presence in K-pop through her work with Red Velvet " \
    "as well as on her show Young Street. For her talent as a singer, her unique beauty, and her " \
    "outgoing and always positive personality, Wendy is my ultimate bias."
  },
  USERNAMES['Diana4Dragons']: {
    'birth_name': "Lee Dong Min (이동민)",
    'birthday': "March 30, 1997",
    'embed_colour': 0x8f0595,
    'filename': "chaeunwoo.jpg",
    'group': "Astro (아스트로)",
    'hometown': "Gunpo, South Korea",
    'name': "Cha Eunwoo (차은우)",
    'position': "Vocalist, Visual",
    'reason': "He started out as a wrecker, but ended up being the one that pulled me deeper " \
    "into Astro. I pretty much binge watched all his dramas back to back on a whim and when I " \
    "ran out I turned to their reality content. I know he isn't the best singer technically, " \
    "but it's his songs that I turn to when I am anxious and need to stay steady. I adore his " \
    "voice. He says he wishes he was funny, but he already is. He isn't afraid to be silly and " \
    "laugh at himself. When he is really happy he just lights up. I didn't know it could be like " \
    "this. For me it's Eunwoo."
  },
  USERNAMES['Kpopbrandy']: {
    'birth_name': "Kim Siyoon (김시윤)",
    'birthday': "February 16, 2005",
    'embed_colour': 0xf0d86a,
    'filename': "billlie_siyoon.jpg",
    'group': "Billlie (빌리)",
    'hometown': "Seoul, South Korea",
    'name': "Siyoon (시윤)",
    'position': "Main Rapper, Lead Dancer",
    'reason': "I thought long and hard about this and with all the things I have and who and " \
    "what I talk about most often it had to be Siyoon. I have the most items of her, I did a " \
    "1:1 video call fansign with her, I have 2 polas and a fat collection of photocards. As " \
    "much as I love Sunny of SNSD And multiple members of Loona, Siyoon had my heart from the " \
    "beginning of RINGXRING and still does. I don't think I've fallen so wholeheartedly for an " \
    "idol since I found Kpop in 2010. Sunny will always be my 1st Bias but as of 2023 Siyoon is " \
    "my ultimate Bias!!! I am a Belllie've to my core and as Siyoon once said \"I'M SO HAPPY " \
    "NOW!\" And with the knowledge that she still remembered my scream of \"I love you, " \
    "Siyoon!\" 3 whole months later, I'll continue to be happy as long as I know her."
  },
  USERNAMES['Xion Rin']: {
    'birth_name': "Lim Nayoung (임나영)",
    'birthday': "December 18, 1995",
    'embed_colour': 0xf24130,
    'filename': "pristin_nayoung.jpeg",
    'group': "Pristin (프리스틴)",
    'hometown': "Seoul, South Korea",
    'name': "Nayoung (나영)",
    'position': "Main Dancer, Lead Rapper",
    'reason': "I think there's something special in your first real love when getting into " \
    "anything, and Nayoung was that for me. I got into kpop by watching the first season of " \
    "Produce 101 and I only had one choice the entire show. Lim Nayoung. I watched her grow, " \
    "I watched her debut, and then redebut, and now I go out of my way to watch every single " \
    "project she does and buy any bit of merch I can. It's hard to explain why I love her so " \
    "much, but she's been there from the beginning and I'm not leaving her side any time soon."
  },
  USERNAMES['Volt D. Resin']: {
    'birth_name': "Yoo Jeongyeon (유정연)",
    'birthday': "November 1, 1996",
    'embed_colour': 0xa3cc54,
    'filename': "twice_jeongyeon.png",
    'group': "Twice (트와이스)",
    'hometown': "Suwon, South Korea",
    'name': "Jeongyeon (정연)",
    'position': "Lead Vocalist",
    'reason': "Funny enough, she wasn't my first ult bias in Twice. It was actually Sana, but " \
    "I never understood what ultimate bias truly meant until that one clip of Jeongyeon getting " \
    "really emotional when Nayeon gave her a gift. To me, that was the realest moment that I've " \
    "ever seen her at. She's normally joking around, but when she cried, I felt that I'm seeing " \
    "who she truly is at that moment. And from that moment, she's been my ultimate bias. Yes, I " \
    "may display Sieun as my profile pic, but at the end of the day, I'm still a Jeongyeon ult " \
    "at heart."
  },
  USERNAMES['Alexrandia']: {
    'birth_name': "Kang Yuchan (강유찬)",
    'birthday': "December 31, 1997",
    'embed_colour': 0xa32921,
    'filename': "ace_yuchan.png",
    'group': "A.C.E (에이스)",
    'hometown': "Jeju, South Korea",
    'name': "Kang Yuchan (강유찬)",
    'position': "Main Vocalist",
    'reason': "There are so many reasons I love Chan! He's handsome, a great dancer, and has a " \
    "voice like honey. He excels at any concept; strong, sweet, emotional, or sexy. More than " \
    "anything, though, it's his energy. Chan is sunshine incarnate and his members say he keeps " \
    "them going when they feel down. His smile is guaranteed to brighten my day and his laugh is " \
    "pure serotonin! Chanshine, Channie, Tangerine Boy, Cutie Maknae Chan...Kang Yuchan is my " \
    "ultimate bias."
  },
}

@discord.app_commands.command(name='my-ultimate-bias', description="See who everyone's ultimate bias is!")
@discord.app_commands.describe(member='The member whose bias you want to see. ' \
                               'Leave empty for your own.')
async def ultimate_bias(interaction: discord.Interaction, member: typing.Optional[str]):
    user_id, username, invalid_member = _user_info_from_interaction(interaction, member)
    if invalid_member:
        await interaction.response.send_message(
            f"Sorry {interaction.user.mention}, {member} hasn't unlocked an ultimate bias yet!",
            ephemeral=True)
        return

    bias_info = ULTIMATE_BIAS_MAP.get(str(user_id))
    if bias_info is None:
        await interaction.response.send_message(
            f"Sorry {interaction.user.mention}, you haven't unlocked an ultimate bias yet!",
            ephemeral=True)
    else:
        bias_image = discord.File(f"iu/media/images/{bias_info.get('filename')}",
                                  filename=bias_info.get('filename'))
        embed = discord.Embed(
            title=f"{username}'s Ultimate Bias",
            type='rich',
            color=bias_info.get('embed_colour'))
        embed.set_image(url=f"attachment://{bias_info.get('filename')}")
        embed.add_field(name="", value='\n'.join([
                f'**Name:** {bias_info.get("name")}',
                f'**Birth Name:** {bias_info.get("birth_name")}',
                f'**Group:** {bias_info.get("group")}',
                f'**Position:** {bias_info.get("position")}',
                f'**Birthday:** {bias_info.get("birthday")}',
                f'**Hometown:** {bias_info.get("hometown")}',
                f'\n**Why {bias_info.get("name")}?**',
                bias_info.get('reason')
            ]))

        await interaction.response.send_message('',
            embed=embed,
            file=bias_image
        )

@discord.app_commands.command(name='my-bias-group', description="See who everyone's bias group is!")
@discord.app_commands.describe(member='The member whose bias group you want to see.' \
                               'Leave empty for your own.')
async def bias_group(interaction: discord.Interaction, member: typing.Optional[str]):
    user_id, username, invalid_member = _user_info_from_interaction(interaction, member)
    if invalid_member:
        await interaction.response.send_message(
            f"Sorry {interaction.user.mention}, {member} hasn't unlocked a bias group yet!",
            ephemeral=True)
        return

    bias_info = ARTIST_BIAS_MAP.get(str(user_id))
    if bias_info is None:
        await interaction.response.send_message(
            f"Sorry {interaction.user.mention}, you haven't unlocked a bias group yet!",
            ephemeral=True)
    else:
        bias_image = discord.File(f"iu/media/images/{bias_info.get('filename')}",
                                  filename=bias_info.get('filename'))
        embed = discord.Embed(
            title=f"{username}'s Bias Group",
            type='rich',
            color=bias_info.get('embed_colour'))
        embed.set_image(url=f"attachment://{bias_info.get('filename')}")
        embed.add_field(name="", value='\n'.join([
            '**Group Info**',
            f"**Name:** {bias_info.get('name')}",
            f"**Members:** {bias_info.get('members')}",
            f"**Label:** {bias_info.get('label')}",
            f"**Debut Date:** {bias_info.get('debut_date')}",
            f"\n**{username}'s Favourites**",
            f"**Bias:** {bias_info.get('bias')}",
            f"**Title Track:** {bias_info.get('title_track')}",
            f"**B Track:** {bias_info.get('b_track')}",
            f"**Album:** {bias_info.get('album')}",
            f"\n**Why {bias_info.get('name')}?**",
            f"{bias_info.get('reason')}",
        ]))

        await interaction.response.send_message('',
            embed=embed,
            file=bias_image
        )

def _user_info_from_interaction(interaction, member_name):
    invalid_member_name = False
    user_id = interaction.user.id
    username = interaction.user.nick if interaction.user.nick else \
        interaction.user.display_name if interaction.user.display_name else \
        interaction.user.global_name

    if member_name:
        for display, username_id in USERNAMES.items():
            if display.lower() == member_name.lower():
                return username_id, display, False
        invalid_member_name = True

    return user_id, username, invalid_member_name
