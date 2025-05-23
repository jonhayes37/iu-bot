"""/my-ultimate-bias command"""

import discord
from common.discord_ids import USERNAMES
from common.user import user_info_from_interaction

BIAS_MAP = {
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
}

async def my_ultimate_bias(interaction, member_name):
    user_id, username, invalid_member = user_info_from_interaction(interaction, member_name)
    if invalid_member:
        await interaction.response.send_message(
            f"Sorry <@!{user_id}>, {member_name} hasn't unlocked an ultimate bias yet!")
        return

    bias_info = BIAS_MAP.get(str(user_id))
    if bias_info is None:
        await interaction.response.send_message(
            f"Sorry <@!{user_id}>, you haven't unlocked an ultimate bias yet!")
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
