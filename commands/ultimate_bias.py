import discord

USERNAME_MAP = {
  "Chris Prime!": "227092770110570496",
  "Diana4Dragons": "797897851907866665",
  "HallyU": "904751089633615972",
  "Kpopbrandy": "202927629018333184",
  "Xion Rin": "271060400886251530",
}

BIAS_MAP = {
  # HallyU
  "904751089633615972": {
    'birth_name': "Seo Juhyun (서주현)",
    'birthday': "June 28, 1991",
    'embed_colour': 0xff4980,
    'filename': "seohyun.jpg",
    'group': "Girls' Generation (소녀시대)",
    'hometown': "Seoul, South Korea",
    'name': "Seohyun (서현)",
    'position': "Maknae, Lead Vocalist",
    'reason': "She was my first bias, and the start of it all! A talented musician, angelic vocalist, stunning visual and hilarious troublemaker <:snsd:795873457086791741>"
  },
  # ChrisPrime
 "227092770110570496": {
    'birth_name': "Son Seung Wan (손승완)",
    'birthday': "February 21, 1994",
    'embed_colour': 0x0070b8,
    'filename': "wendy.jpg",
    'group': "Red Velvet (레드벨벳)",
    'hometown': "Seoul, South Korea",
    'name': "Wendy (웬디)",
    'position': "Main Vocalist",
    'reason': "I keep going back to the emptiness I felt during the year of hell when Wendy was absent from activities due to injuries, and how I felt the first time she returned to perform live again with the rest of the 'group'. It was a feeling of indescribable and unrestrained bliss. She's not only one of if not the best third gen main vocal, but she continues to be a positive influence and presence in K-pop through her work with Red Velvet as well as on her show Young Street. For her talent as a singer, her unique beauty, and her outgoing and always positive personality, Wendy is my ultimate bias."
  },
  # Diana4Dragons
  "797897851907866665": {
    'birth_name': "Lee Dong Min (이동민)",
    'birthday': "March 30, 1997",
    'embed_colour': 0x8f0595,
    'filename': "chaeunwoo.jpg",
    'group': "Astro (아스트로)",
    'hometown': "Gunpo, South Korea",
    'name': "Cha Eunwoo (차은우)",
    'position': "Vocalist, Visual",
    'reason': "He started out as a wrecker, but ended up being the one that pulled me deeper into Astro. I pretty much binge watched all his dramas back to back on a whim and when I ran out I turned to their reality content. I know he isn’t the best singer technically, but it’s his songs that I turn to when I am anxious and need to stay steady. I adore his voice. He says he wishes he was funny, but he already is. He isn’t afraid to be silly and laugh at himself. When he is really happy he just lights up. I didn’t know it could be like this. For me it’s Eunwoo."
  },
  # Kpopbrandy
  "202927629018333184": {
    'birth_name': "Kim Siyoon (김시윤)",
    'birthday': "February 16, 2005",
    'embed_colour': 0xf0d86a,
    'filename': "billlie_siyoon.jpg",
    'group': "Billlie (빌리)",
    'hometown': "Seoul, South Korea",
    'name': "Siyoon (시윤)",
    'position': "Main Rapper, Lead Dancer",
    'reason': "I thought long and hard about this and with all the things I have and who and what I talk about most often it had to be Siyoon. I have the most items of her, I did a 1:1 video call fansign with her, I have 2 polas and a fat collection of photocards. As much as I love Sunny of SNSD And multiple members of Loona, Siyoon had my heart from the beginning of RINGXRING and still does. I don't think I've fallen so wholeheartedly for an idol since I found Kpop in 2010. Sunny will always be my 1st Bias but as of 2023 Siyoon is my ultimate Bias!!! I am a Belllie've to my core and as Siyoon once said \"I'M SO HAPPY NOW!\" And with the knowledge that she still remembered my scream of \"I love you, Siyoon!\" 3 whole months later, I'll continue to be happy as long as I know her."
  },
  # Xion Rin
  "271060400886251530": {
    'birth_name': "Lim Nayoung (임나영)",
    'birthday': "December 18, 1995",
    'embed_colour': 0xf24130,
    'filename': "pristin_nayoung.jpeg",
    'group': "Pristin (프리스틴)",
    'hometown': "Seoul, South Korea",
    'name': "Nayoung (나영)",
    'position': "Main Dancer, Lead Rapper",
    'reason': "I think there's something special in your first real love when getting into anything, and Nayoung was that for me. I got into kpop by watching the first season of Produce 101 and I only had one choice the entire show. Lim Nayoung. I watched her grow, I watched her debut, and then redebut, and now I go out of my way to watch every single project she does and buy any bit of merch I can. It's hard to explain why I love her so much, but she's been there from the beginning and I'm not leaving her side any time soon."
  },
}

async def my_ultimate_bias(interaction, member_name):
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
            await interaction.response.send_message(f"Sorry <@!{user_id}>, {member_name} hasn't unlocked an ultimate bias yet!")
            return

    bias_info = BIAS_MAP.get(str(user_id))
    if bias_info is None:
        await interaction.response.send_message(f"Sorry <@!{user_id}>, you haven't unlocked an ultimate bias yet!")
    else:
        bias_image = discord.File(f"media/images/{bias_info.get('filename')}", filename=bias_info.get('filename'))
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
