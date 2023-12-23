"""Unit testing for bias_group.py"""

import discord
import pytest
from commands.bias_group import my_bias_group
from testing.interaction import MockInteraction, MockUser
from common.discord_ids import USERNAMES

main_user = MockUser(id=USERNAMES["HallyU"], name="soshi0805", nick="HallyU")
not_unlocked_user = MockUser(id="12345", name="soshi", nick="Soshi")
main_file = discord.File("iu/media/images/snsd.jpg", filename='snsd.jpg')
main_embed = discord.Embed(title="HallyU's Bias Group",
    type='rich',
    color=0xff4980,
)
main_embed.set_image(url='attachment://snsd.jpg')
main_embed.add_field(name='', value="""**Group Info**
**Name:** Girls' Generation (소녀시대)
**Members:** Hyoyeon, Seohyun, Sooyoung, Sunny, Taeyeon, Tiffany, Yoona, Yuri
**Label:** SM Entertainment
**Debut Date:** August 5, 2007

**HallyU's Favourites**
**Bias:** Seohyun
**Title Track:** [Into The New World (다시 만난 세계)](https://youtu.be/0k2Zzkw_-0I)
**B Track:** [Lucky Like That](https://youtu.be/THDVlS51ywI)
**Album:** [Girls & Peace](https://youtu.be/xVYXTEG0Qeg)

**Why Girls' Generation (소녀시대)?**
The Nation's Girl Group! These girls and their body of work speaks for itself. Nobody did it like them.
*Right now, Girls' Generation*
*From now on, Girls' Generation*
*Forever, Girls' Generation*
<:snsd:795873457086791741>""")

@pytest.mark.asyncio()
@pytest.mark.parametrize(["user", "member", "expected_message", "expected_embed", "expected_file"],
[
    # User doesn't have command unlocked
    (not_unlocked_user, "", f"Sorry <@!{not_unlocked_user.id}>, you haven't unlocked a bias group yet!", None, None),
    # Non-existent member
    (main_user, "Soshified", f"Sorry <@!{main_user.id}>, Soshified hasn't unlocked a bias group yet!", None, None),
    # Run on self (no member)
    (main_user, "", "", main_embed, main_file),
])
async def test_bias_group(user, member, expected_message, expected_embed, expected_file):
    interaction = MockInteraction(user)
    await my_bias_group(interaction, member)

    interaction.assert_message_equals(expected_message)
    interaction.assert_embed_equals(expected_embed)
    interaction.assert_file_equals(expected_file)
