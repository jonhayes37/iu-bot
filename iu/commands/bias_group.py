"""/my-bias-group command"""

import discord
from common.discord_ids import USERNAMES
from common.user import user_info_from_interaction

BIAS_MAP = {
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

async def my_bias_group(interaction, member_name):
    user_id, username, invalid_member = user_info_from_interaction(interaction, member_name)
    if invalid_member:
        await interaction.response.send_message(
            f"Sorry <@!{user_id}>, {member_name} hasn't unlocked a bias group yet!")
        return

    bias_info = BIAS_MAP.get(str(user_id))
    if bias_info is None:
        await interaction.response.send_message(
            f"Sorry <@!{user_id}>, you haven't unlocked a bias group yet!")
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
