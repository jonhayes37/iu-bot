import discord

USERNAME_MAP = {
  "Alexrandia": "453573453623328778",
  "Chris Prime!": "227092770110570496",
  "Diana4Dragons": "797897851907866665",
  "HallyU": "904751089633615972",
  "Stromsolar": "317621715247300609",
  "Kpopbrandy": "202927629018333184",
  "Xion Rin": "271060400886251530",
}

BIAS_MAP = {
  # HallyU
  "904751089633615972": {
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
      "The Nation's Girl Group! These girls and their body of work speaks for itself. Nobody did it like them.",
      "*Right now, Girls' Generation*",
      "*From now on, Girls' Generation*",
      "*Forever, Girls' Generation*",
      "<:snsd:795873457086791741>"
    ]),
    'title_track': "[Into The New World (다시 만난 세계)](https://youtu.be/0k2Zzkw_-0I)",
  },
  # ChrisPrime
  "227092770110570496": {
    'album': "[Time For Us](https://youtu.be/i6rIeFM9kfo)",
    'bias': "Yuju (she's so weird, yet graceful and elegant and is an absolutely top tier vocalist)",
    'b_track': "[You Are My Star](https://youtu.be/3EKLdmyPyVs), [Wheel of the Year](https://youtu.be/tiiu8LhmHcE)",
    'debut_date': "January 15, 2015",
    'embed_colour': 0x00b2ca,
    'filename': "gfriend.jpg",
    'label': "Source Music",
    'members': "Eunha, SinB, Sowon, Umji, Yerin, Yuju",
    'name': "GFriend (여자친구)",
    'reason': '\n'.join([
      "There's something so special about them as a group. They're one of a very few K-pop groups that MADE trends rather than chasing them, they have one of the most solid and expansive discographies in K-pop, the well-earned title of Queens of Synchronization, and they have the respect of just about everybody in the industry. I might not Stan them as hard as I used to since their disbandment, but in my heart they'll always be number 1.",
    ]),
    'title_track': "[Mago](https://youtu.be/LmBYPXGqtss), [Rainbow](https://youtu.be/ZSXN_dpG5jk)",
  },
  # Diana4Dragons
  "797897851907866665": {
    'album': "[Love Yourself Answer](https://youtu.be/A65TAHQqU6I)",
    'bias': "Jin",
    'b_track': "[Answer: Love Myself](https://youtu.be/9mwRYgMmSGE), [Moon](https://youtu.be/F5H3g0UR7CI)",
    'debut_date': "June 12, 2013",
    'embed_colour': 0x69448e,
    'filename': "bts.jpg",
    'label': "Big Hit Music",
    'members': "J-Hope, Jimin, Jin, Jungkook, RM, Suga, V",
    'name': "BTS (방탄소년단)",
    'reason': '\n'.join([
      "BTS is the group that first made me interested in and care about the members as people and not just the music. They are the only group where all of the members are high on my bias list. I love a lot of their discography to the point that answering about my favourites was a process that took days - and there are still two b-sides.",
      "<:bts:800437846367928341>"
    ]),
    'title_track': "[Blood Sweat & Tears](https://youtu.be/hmE9f-TEutc)",
  },
  # Xion Rin
  "271060400886251530": {
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
      "Pristin was the first group I was truly, 100% invested in when it came to Kpop. Their level of talent, their personalities and how clearly they all loved each other just stole my heart and even though they weren't together long, you can tell these girls still love each other so much.",
      "<:pristin:838245257447604255>"
    ]),
    'title_track': "[We Like](https://youtu.be/J6LAzgZi8N8)",
  },
  # Alexrandia
  "453573453623328778": {
    'album': "[Siren: Dawn](https://youtu.be/DVDMq5q8SzE)",
    'bias': "OT5! (Every member constantly wrecks me, so I gave in to them all.)",
    'b_track': "[Clover](https://youtu.be/-UgUWK6GLic), [Chasing Love](https://youtu.be/3cGmnsAWinU)",
    'debut_date': "May 23, 2017",
    'embed_colour': 0x23a55a,
    'filename': "ace.jpg",
    'label': "Beat Interactive",
    'members': "Byeongkwan, Chan, Donghun, Jun, Wow",
    'name': "A.C.E (에이스)",
    'reason': '\n'.join([
      "I never fan-girled in my life before I found A.C.E, but they deserve it in so many ways. Their talent, their aesthetic, their personalities, and their open support for the LGBTQ+ community. They can pull off any concept and have a song for every mood.",
      "<:ace:837490788216078356>"
    ]),
    'title_track': "[Under Cover](https://youtu.be/qODWFe6v3zA)",
  },
  # Kpopbrandy
  "202927629018333184": {
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
      "I found Billlie through Sheon and GP999.  Knowing she was going to join them initially got me interested but this group is so magnetic once I fell for them I knew I would be in it for life.  The music is absolutely Mystical! (Yes that is a play on them being in Mystic Story!)",
      "<:billlie:915261590452985946>"
    ]),
    'title_track': "[RING x RING](https://youtu.be/i9jhxOwcaw0)",
  },
  # Stromsolar
  "317621715247300609": {
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
      "<:gidle:795876356491575318> is the group that got me into Kpop. I like the fact that this is a self product group. I love their concept that consist in creating a unique group by having members with very different charms/abilities and by fully using those abilities in every single song. They are always able to create songs with new and original concepts while having a distinctive style."
    ]),
    'title_track': "[Lion](https://youtu.be/6oanIo_2Z4Q)",
  }
}


async def my_bias_group(interaction, member_name):
    user_id = interaction.user.id
    username = interaction.user.nick if interaction.user.nick else \
        interaction.user.display_name if interaction.user.display_name else interaction.user.global_name

    # Check for the person requested in the option
    if member_name:
        member_found = False
        for display, id in USERNAME_MAP.items():
            if display.lower() == member_name.lower():
                user_id = id
                username = display
                member_found = True
                break
        if not member_found:
            await interaction.response.send_message(f"Sorry <@!{user_id}>, {member_name} hasn't unlocked a bias group yet!")
            return

    bias_info = BIAS_MAP.get(str(user_id))
    if bias_info is None:
        await interaction.response.send_message(f"Sorry <@!{user_id}>, you haven't unlocked a bias group yet!")
    else:
        bias_image = discord.File(f"media/images/{bias_info.get('filename')}", filename=bias_info.get('filename'))
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
