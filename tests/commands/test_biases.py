"""Tests for commands/biases.py: showing members' bias cards."""

import pytest

from commands.biases import (
    bias_group, create_bias_group, create_ultimate_bias, ultimate_bias, update_bias_group, update_ultimate_bias
)
from config import Database
from db.biases import create_artist_bias_db, create_ultimate_bias_db, get_artist_bias, get_ultimate_bias

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


@pytest.mark.parametrize("command", [ultimate_bias, bias_group])
class TestMembersWithoutACard:
    """Nobody has unlocked a card yet."""

    async def test_someone_without_a_card_is_told_privately_and_nothing_is_uploaded(self, interaction, command):
        await command.callback(interaction)

        [reply] = interaction.sent
        assert reply.via == "response" and reply.ephemeral
        assert "you haven't unlocked" in reply.content
        interaction.response.defer.assert_not_awaited()

    async def test_asking_about_a_member_without_a_card_names_them(self, interaction, make_member, command):
        friend = make_member(user_id=777, name="Friend")

        await command.callback(interaction, friend)

        assert "Friend hasn't unlocked" in interaction.sent[0].content


ULTIMATE = {"name": "Seohyun", "birth_name": "Seo Juhyun", "group_name": "Girls' Generation", "position": "Maknae",
            "birthday": "June 28, 1991", "hometown": "Seoul", "colour_hex": "#ff4980", "image_filename": IMAGE,
            "reason": "Because"}
GROUP = {"name": "IVE", "members": "Yujin, Gaeul", "label": "Starship", "debut_date": "Dec 1, 2021",
         "bias": "Wonyoung", "title_track": "Eleven", "b_track": "Royalty", "album": "Love Dive",
         "colour_hex": "0x123456", "image_filename": IMAGE, "reason": "Why not"}


class TestCreateUltimateBias:
    """/create-ultimate-bias (admin)."""

    async def test_creates_the_card(self, admin_interaction, make_member):
        member = make_member(user_id=50)

        await create_ultimate_bias.callback(admin_interaction, member, **ULTIMATE)

        card = get_ultimate_bias(50)
        assert (card["name"], card["colour"], card["image_filename"]) == ("Seohyun", 0xFF4980, IMAGE)
        [reply] = admin_interaction.sent
        assert reply.content == f"Successfully created the Ultimate Bias entry for {member.mention}!"
        assert reply.ephemeral

    async def test_a_member_who_already_has_one_is_pointed_to_the_update_command(self, admin_interaction, make_member):
        member = make_member(user_id=50)
        _make_ultimate(50)

        await create_ultimate_bias.callback(admin_interaction, member, **ULTIMATE)

        assert admin_interaction.sent[0].content == (
            f"Nothing was created: {member.mention} already has an Ultimate Bias recorded. "
            "Use `/update-ultimate-bias` instead.")

    @pytest.mark.parametrize("colour", ["zzzzzz", "1000000", ""])
    async def test_a_colour_discord_cannot_show_is_refused(self, admin_interaction, make_member, colour):
        await create_ultimate_bias.callback(admin_interaction, make_member(user_id=50),
                                            **{**ULTIMATE, "colour_hex": colour})

        assert admin_interaction.sent[0].content.startswith("Invalid hex colour.")
        assert get_ultimate_bias(50) is None

    @pytest.mark.parametrize("image", ["missing.jpg", "../config.py", "sub/dir.jpg"])
    async def test_a_picture_that_is_not_in_the_images_folder_is_refused(self, admin_interaction, make_member, image):
        await create_ultimate_bias.callback(admin_interaction, make_member(user_id=50),
                                            **{**ULTIMATE, "image_filename": image})

        assert admin_interaction.sent[0].content == (
            f"❌ There is no image called `{image}` in the images folder. Use just the file name.")
        assert get_ultimate_bias(50) is None


class TestUpdateUltimateBias:
    """/update-ultimate-bias (admin) changes only the fields given."""

    async def test_updates_only_what_was_given(self, admin_interaction, make_member):
        member = make_member(user_id=50)
        _make_ultimate(50)

        await update_ultimate_bias.callback(admin_interaction, member, reason="A better reason", colour_hex="#000001")

        card = get_ultimate_bias(50)
        assert (card["reason"], card["colour"], card["name"]) == ("A better reason", 1, "Seohyun")
        assert admin_interaction.sent[0].content == \
            f"Successfully updated the Ultimate Bias entry for {member.mention}!"

    async def test_nothing_to_update(self, admin_interaction, make_member):
        _make_ultimate(50)

        await update_ultimate_bias.callback(admin_interaction, make_member(user_id=50))

        assert admin_interaction.sent[0].content == "You didn't provide any fields to update!"

    async def test_a_member_without_a_card_is_pointed_to_the_create_command(self, admin_interaction, make_member):
        member = make_member(user_id=50)

        await update_ultimate_bias.callback(admin_interaction, member, reason="x")

        assert admin_interaction.sent[0].content == (
            f"Failed to update entry. {member.mention} does not have an Ultimate Bias recorded yet. "
            "Use `/create-ultimate-bias` first.")

    async def test_a_bad_colour_or_picture_changes_nothing(self, admin_interaction, make_member):
        _make_ultimate(50)

        await update_ultimate_bias.callback(admin_interaction, make_member(user_id=50), reason="new",
                                            colour_hex="nope")
        await update_ultimate_bias.callback(admin_interaction, make_member(user_id=50), reason="new",
                                            image_filename="missing.jpg")

        assert get_ultimate_bias(50)["reason"] == "Because"
        assert len(admin_interaction.sent) == 2


class TestCreateBiasGroup:
    """/create-bias-group (admin)."""

    async def test_creates_the_card(self, admin_interaction, make_member):
        member = make_member(user_id=50)

        await create_bias_group.callback(admin_interaction, member, **GROUP)

        card = get_artist_bias(50)
        assert (card["name"], card["colour"], card["title_track"]) == ("IVE", 0x123456, "Eleven")
        assert admin_interaction.sent[0].content == f"Successfully created the Bias Group entry for {member.mention}!"

    async def test_a_member_who_already_has_one(self, admin_interaction, make_member):
        member = make_member(user_id=50)
        _make_group(50)

        await create_bias_group.callback(admin_interaction, member, **GROUP)

        assert admin_interaction.sent[0].content == (
            f"Nothing was created: {member.mention} already has an entry. Use `/update-bias-group`.")

    async def test_a_bad_colour_is_refused(self, admin_interaction, make_member):
        await create_bias_group.callback(admin_interaction, make_member(user_id=50), **{**GROUP, "colour_hex": "x"})

        assert admin_interaction.sent[0].content.startswith("Invalid hex colour.")
        assert get_artist_bias(50) is None

    async def test_a_missing_picture_is_refused(self, admin_interaction, make_member):
        await create_bias_group.callback(admin_interaction, make_member(user_id=50),
                                         **{**GROUP, "image_filename": "missing.jpg"})

        assert "There is no image called `missing.jpg`" in admin_interaction.sent[0].content
        assert get_artist_bias(50) is None


class TestUpdateBiasGroup:
    """/update-bias-group (admin) changes only the fields given."""

    async def test_updates_only_what_was_given(self, admin_interaction, make_member):
        member = make_member(user_id=50)
        _make_group(50)

        await update_bias_group.callback(admin_interaction, member, bias="Rei", colour_hex="ffffff")

        card = get_artist_bias(50)
        assert (card["bias"], card["colour"], card["name"]) == ("Rei", 0xFFFFFF, "IVE")
        assert admin_interaction.sent[0].content == f"Successfully updated the Bias Group entry for {member.mention}!"

    async def test_nothing_to_update(self, admin_interaction, make_member):
        _make_group(50)

        await update_bias_group.callback(admin_interaction, make_member(user_id=50))

        assert admin_interaction.sent[0].content == "⚠️ You didn't provide any fields to update!"

    async def test_a_member_without_a_card(self, admin_interaction, make_member):
        member = make_member(user_id=50)

        await update_bias_group.callback(admin_interaction, member, bias="Rei")

        assert admin_interaction.sent[0].content == \
            f"Update failed. {member.mention} does not have a Bias Group recorded yet."

    async def test_a_bad_colour_changes_nothing(self, admin_interaction, make_member):
        _make_group(50)

        await update_bias_group.callback(admin_interaction, make_member(user_id=50), bias="Rei", colour_hex="nope")

        assert get_artist_bias(50)["bias"] == "Wonyoung"
