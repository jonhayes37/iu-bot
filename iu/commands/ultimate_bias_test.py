"""Unit testing for ultimate_bias.py"""

import discord
import pytest
from commands.ultimate_bias import my_ultimate_bias
from common.discord_ids import USERNAMES
from testing.interaction import MockInteraction, MockUser

main_user = MockUser(user_id=USERNAMES["HallyU"], name="soshi0805", nick="HallyU")
not_unlocked_user = MockUser(user_id="12345", name="soshi", nick="Soshi")
main_file = discord.File("iu/media/images/seohyun.jpg", filename='seohyun.jpg')
main_embed = discord.Embed(title="HallyU's Ultimate Bias",
    type='rich',
    color=0xff4980,
)
main_embed.set_image(url='attachment://seohyun.jpg')
main_embed.add_field(name='', value="""**Name:** Seohyun (서현)
**Birth Name:** Seo Juhyun (서주현)
**Group:** Girls' Generation (소녀시대)
**Position:** Maknae, Lead Vocalist
**Birthday:** June 28, 1991
**Hometown:** Seoul, South Korea

**Why Seohyun (서현)?**
She was my first bias, and the start of it all! A talented musician, """ \
"""angelic vocalist, stunning visual and hilarious troublemaker <:snsd:795873457086791741>""")

@pytest.mark.asyncio()
@pytest.mark.parametrize(["user", "member", "expected_message", "expected_embed", "expected_file"],
[
    # User doesn't have command unlocked
    (not_unlocked_user,
     "",
     f"Sorry <@!{not_unlocked_user.id}>, you haven't unlocked an ultimate bias yet!",
     None,
     None),
    # Non-existent member
    (main_user,
     "Soshified",
     f"Sorry <@!{main_user.id}>, Soshified hasn't unlocked an ultimate bias yet!",
     None,
     None),
    # Run on self (no member)
    (main_user,
     "",
     "",
     main_embed,
     main_file),
])
async def test_ultimate_bias(user, member, expected_message, expected_embed, expected_file):
    interaction = MockInteraction(user)
    await my_ultimate_bias(interaction, member)

    interaction.assert_message_equals(expected_message)
    interaction.assert_embed_equals(expected_embed)
    interaction.assert_file_equals(expected_file)
