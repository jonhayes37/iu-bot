"""Tests for commands/biases.py: showing members' bias cards."""

import pytest

from commands.biases import bias_group, ultimate_bias
from config import Database
from db.biases import create_artist_bias_db, create_ultimate_bias_db

IMAGE = "gidle.jpg"          # a real file in iu/media/images


@pytest.fixture(autouse=True)
def _biases_database(databases):
    databases(Database.BIASES)


def _make_ultimate(user_id, image=IMAGE):
    create_ultimate_bias_db(user_id, "Seohyun", "Seo Juhyun", "June 28, 1991", 0xFF4980, "Girls' Generation",
                            "Seoul", image, "Maknae", "Because")


def _make_group(user_id, image=IMAGE):
    create_artist_bias_db(user_id, "IVE", "Love Dive", "Royalty", "Wonyoung", 0x123456, "Dec 1, 2021", image,
                          "Starship", "Yujin, Gaeul", "Why not", "Eleven")


@pytest.mark.parametrize("command, make", [(ultimate_bias, _make_ultimate), (bias_group, _make_group)])
class TestShowingABiasCard:
    """/my-ultimate-bias and /my-bias-group."""

    async def test_the_card_is_acknowledged_before_the_picture_is_uploaded(self, interaction, command, make):
        # The picture upload can take longer than the 3 seconds Discord allows for a first response
        make(interaction.user.id)
        order = []
        interaction.response.defer.side_effect = lambda *a, **k: order.append("defer")
        interaction.followup.send.side_effect = lambda *a, **k: order.append("upload")

        await command.callback(interaction)

        assert order == ["defer", "upload"]
        interaction.response.send_message.assert_not_awaited()

    async def test_the_card_is_sent_as_a_follow_up_with_the_picture(self, interaction, command, make):
        make(interaction.user.id)

        await command.callback(interaction)

        [card] = interaction.sent
        assert card.via == "followup"
        assert card.kwargs["file"].filename == IMAGE
        assert card.embed.image.url == f"attachment://{IMAGE}"
        assert card.embed.title.startswith(f"{interaction.user.display_name}'s")

    async def test_another_members_card_can_be_shown(self, interaction, make_member, command, make):
        friend = make_member(user_id=777, name="Friend")
        make(777)

        await command.callback(interaction, friend)

        assert interaction.sent[0].embed.title.startswith("Friend's")

    async def test_someone_without_a_card_is_told_privately_and_nothing_is_uploaded(self, interaction, command, make):
        await command.callback(interaction)

        [reply] = interaction.sent
        assert reply.via == "response" and reply.ephemeral
        assert "you haven't unlocked" in reply.content
        interaction.response.defer.assert_not_awaited()

    async def test_asking_about_a_member_without_a_card_names_them(self, interaction, make_member, command, make):
        friend = make_member(user_id=777, name="Friend")

        await command.callback(interaction, friend)

        assert "Friend hasn't unlocked" in interaction.sent[0].content

    async def test_a_missing_picture_is_reported_privately(self, interaction, command, make):
        make(interaction.user.id, image="deleted.jpg")

        await command.callback(interaction)

        [reply] = interaction.sent
        assert reply.via == "response" and reply.ephemeral
        assert reply.content == "Error: Could not find image file `deleted.jpg` on the server."
        interaction.response.defer.assert_not_awaited()

    async def test_a_picture_name_that_points_outside_the_images_folder_is_not_used(self, interaction, command, make):
        make(interaction.user.id, image="../config.py")

        await command.callback(interaction)

        assert "Could not find image file" in interaction.sent[0].content
