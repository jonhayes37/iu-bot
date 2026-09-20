"""Commands for bias embeds"""
import typing
from pathlib import Path

import discord
from discord import app_commands
from config import MEDIA_DIR
from db.biases import (
    create_artist_bias_db, create_ultimate_bias_db, get_artist_bias, get_ultimate_bias,
    update_artist_bias_db, update_ultimate_bias_db
)
from utils.validation import admin_only, parse_colour

IMAGES_DIR = MEDIA_DIR / "images"
BAD_COLOUR_TEXT = "Invalid hex colour. Please use a format like `ff4980`, `#ff4980`, or `0xff4980`."


def _image_exists(filename: str) -> bool:
    """True if the name is a plain file name inside the images folder (no folders, no `..`)."""
    return Path(filename).name == filename and (IMAGES_DIR / filename).is_file()


def _image_file(filename: str) -> discord.File | None:
    """The image as an attachment, or None if it is missing or isn't a plain file name."""
    if not _image_exists(filename):
        return None
    return discord.File(IMAGES_DIR / filename, filename=filename)


async def _send_with_image(interaction: discord.Interaction, embed: discord.Embed, image: discord.File):
    """
    Posts an embed with its picture. Uploading the picture can take longer than the 3 seconds Discord
    allows for a first response (a cold connection and a slow upload from the NAS are enough), after
    which the interaction expires and the user sees "The application did not respond". So the response is
    acknowledged first, which is instant, and the picture is sent as the follow-up.
    """
    await interaction.response.defer()
    await interaction.followup.send(embed=embed, file=image)


async def _check_style(interaction: discord.Interaction, colour_hex: str | None,
                       image_filename: str | None) -> tuple[bool, int | None]:
    """
    Validates the optional colour and image name from a create/update command. Returns
    (ok, colour); when not ok the error has already been sent to the admin.
    """
    colour = None
    if colour_hex is not None:
        colour = parse_colour(colour_hex)
        if colour is None:
            await interaction.response.send_message(BAD_COLOUR_TEXT, ephemeral=True)
            return False, None

    if image_filename is not None and not _image_exists(image_filename):
        await interaction.response.send_message(
            f"❌ There is no image called `{image_filename}` in the images folder. Use just the file name.",
            ephemeral=True)
        return False, None

    return True, colour


@app_commands.command(name='my-ultimate-bias', description="See who everyone's ultimate bias is!")
@app_commands.describe(member='The member whose bias you want to see. Leave empty for your own.')
async def ultimate_bias(interaction: discord.Interaction, member: typing.Optional[discord.Member] = None):
    target_user = member or interaction.user
    bias_info = get_ultimate_bias(target_user.id)

    if not bias_info:
        if member:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, {target_user.display_name} hasn't unlocked an ultimate bias yet!",
                ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, you haven't unlocked an ultimate bias yet!",
                ephemeral=True)
        return

    filename = bias_info['image_filename']
    bias_image = _image_file(filename)
    if bias_image is None:
        # Failsafe just in case the DB has a typo or the image was deleted from Unraid
        await interaction.response.send_message(f"Error: Could not find image file `{filename}` on the server.",
                                                ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{target_user.display_name}'s Ultimate Bias",
        type='rich',
        color=bias_info['colour']
    )
    embed.set_image(url=f"attachment://{filename}")
    embed.add_field(name="", value='\n'.join([
        f'**Name:** {bias_info["name"]}',
        f'**Birth Name:** {bias_info["birth_name"]}',
        f'**Group:** {bias_info["group_name"]}',
        f'**Position:** {bias_info["position"]}',
        f'**Birthday:** {bias_info["birthday"]}',
        f'**Hometown:** {bias_info["hometown"]}',
        f'\n**Why {bias_info["name"]}?**',
        bias_info['reason']
    ]))

    await _send_with_image(interaction, embed, bias_image)

@app_commands.command(name="create-ultimate-bias", description="[Admin] Create an ultimate bias record for a user.")
@app_commands.describe(
    member="The server member this ultimate bias belongs to.",
    name="The idol's stage name (e.g., Seohyun)",
    birth_name="The idol's full birth name (e.g., Seo Juhyun)",
    group_name="The idol's group name (e.g., Girls' Generation)",
    position="The idol's role(s) in the group (e.g., Maknae, Lead Vocalist)",
    birthday="The idol's date of birth (e.g., June 28, 1991)",
    hometown="Where the idol is from (e.g., Seoul, South Korea)",
    colour_hex="Hex colour code for the embed (e.g., ff4980 or #ff4980)",
    image_filename="Filename in the local images folder (e.g., seohyun.jpg)",
    reason="Why is this their ultimate bias? (Paste the full text here)"
)
@admin_only
async def create_ultimate_bias(
    interaction: discord.Interaction,
    member: discord.Member,
    name: str,
    birth_name: str,
    group_name: str,
    position: str,
    birthday: str,
    hometown: str,
    colour_hex: str,
    image_filename: str,
    reason: str
):
    """Creates a new ultimate bias entry directly from command arguments."""

    ok, colour_int = await _check_style(interaction, colour_hex, image_filename)
    if not ok:
        return

    # Write to the DB
    success = create_ultimate_bias_db(
        user_id=member.id,
        name=name,
        birth_name=birth_name,
        birthday=birthday,
        colour=colour_int,
        group_name=group_name,
        hometown=hometown,
        image_filename=image_filename,
        position=position,
        reason=reason
    )

    if success:
        await interaction.response.send_message(
            f"Successfully created the Ultimate Bias entry for {member.mention}!",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"Nothing was created: {member.mention} already has an Ultimate Bias "
            "recorded. Use `/update-ultimate-bias` instead.",
            ephemeral=True)

@app_commands.command(name="update-ultimate-bias",
                      description="[Admin] Update specific fields of an existing ultimate bias record.")
@app_commands.describe(
    member="The server member whose record you want to update.",
    name="The idol's stage name",
    birth_name="The idol's full birth name",
    group_name="The idol's group name",
    position="The idol's role(s) in the group",
    birthday="The idol's date of birth",
    hometown="Where the idol is from",
    colour_hex="Hex colour code for the embed",
    image_filename="Exact filename in the local images folder",
    reason="Why is this their ultimate bias?"
)
@admin_only
async def update_ultimate_bias(
    interaction: discord.Interaction,
    member: discord.Member,
    name: typing.Optional[str] = None,
    birth_name: typing.Optional[str] = None,
    group_name: typing.Optional[str] = None,
    position: typing.Optional[str] = None,
    birthday: typing.Optional[str] = None,
    hometown: typing.Optional[str] = None,
    colour_hex: typing.Optional[str] = None,
    image_filename: typing.Optional[str] = None,
    reason: typing.Optional[str] = None
):
    """Updates an existing ultimate bias entry. Only provided fields are changed."""
    provided_args = {
        'name': name,
        'birth_name': birth_name,
        'group_name': group_name,
        'position': position,
        'birthday': birthday,
        'hometown': hometown,
        'image_filename': image_filename,
        'reason': reason
    }
    updates = {k: v for k, v in provided_args.items() if v is not None}

    ok, colour_int = await _check_style(interaction, colour_hex, image_filename)
    if not ok:
        return
    if colour_int is not None:
        updates['colour'] = colour_int

    if not updates:
        await interaction.response.send_message(
            "You didn't provide any fields to update!", 
            ephemeral=True
        )
        return

    success = update_ultimate_bias_db(member.id, **updates)
    if success:
        await interaction.response.send_message(
            f"Successfully updated the Ultimate Bias entry for {member.mention}!",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"Failed to update entry. {member.mention} does not have an Ultimate Bias recorded yet. "
            "Use `/create-ultimate-bias` first.",
            ephemeral=True)

@app_commands.command(name="create-bias-group", description="[Admin] Create a bias group record for a user.")
@app_commands.describe(
    member="The server member this bias group belongs to.",
    name="The group's name (e.g., Girls' Generation)",
    members="Comma-separated list of members",
    label="The group's company/label",
    debut_date="The group's debut date",
    bias="The user's bias in this group",
    title_track="The user's favourite title track (URLs supported)",
    b_track="The user's favourite b-side track (URLs supported)",
    album="The user's favourite album (URLs supported)",
    colour_hex="Hex colour code for the embed",
    image_filename="Exact filename in the local images folder",
    reason="Why is this their bias group?"
)
@admin_only
async def create_bias_group(
    interaction: discord.Interaction,
    member: discord.Member,
    name: str,
    members: str,
    label: str,
    debut_date: str,
    bias: str,
    title_track: str,
    b_track: str,
    album: str,
    colour_hex: str,
    image_filename: str,
    reason: str
):
    ok, colour_int = await _check_style(interaction, colour_hex, image_filename)
    if not ok:
        return

    success = create_artist_bias_db(
        user_id=member.id, name=name, album=album, b_track=b_track, bias=bias,
        colour=colour_int, debut_date=debut_date, image_filename=image_filename,
        label=label, members=members, reason=reason, title_track=title_track
    )

    if success:
        await interaction.response.send_message(f"Successfully created the Bias Group entry for {member.mention}!",
                                                ephemeral=True)
    else:
        await interaction.response.send_message(
            f"Nothing was created: {member.mention} already has an entry. Use `/update-bias-group`.",
            ephemeral=True)

@app_commands.command(name="update-bias-group",
                      description="[Admin] Update specific fields of an existing bias group record.")
@app_commands.describe(
    member="The server member whose record you want to update.",
    name="The group's name",
    members="Comma-separated list of members",
    label="The group's company/label",
    debut_date="The group's debut date",
    bias="The user's bias in this group",
    title_track="The user's favourite title track (URLs supported)",
    b_track="The user's favourite b-side track (URLs supported)",
    album="The user's favourite album (URLs supported)",
    colour_hex="Hex colour code for the embed",
    image_filename="Exact filename in the local images folder",
    reason="Why is this their bias group?"
)
@admin_only
async def update_bias_group(
    interaction: discord.Interaction,
    member: discord.Member,
    name: typing.Optional[str] = None,
    members: typing.Optional[str] = None,
    label: typing.Optional[str] = None,
    debut_date: typing.Optional[str] = None,
    bias: typing.Optional[str] = None,
    title_track: typing.Optional[str] = None,
    b_track: typing.Optional[str] = None,
    album: typing.Optional[str] = None,
    colour_hex: typing.Optional[str] = None,
    image_filename: typing.Optional[str] = None,
    reason: typing.Optional[str] = None
):
    provided_args = {
        'name': name, 'members': members, 'label': label, 'debut_date': debut_date,
        'bias': bias, 'title_track': title_track, 'b_track': b_track, 'album': album,
        'image_filename': image_filename, 'reason': reason
    }
    updates = {k: v for k, v in provided_args.items() if v is not None}

    ok, colour_int = await _check_style(interaction, colour_hex, image_filename)
    if not ok:
        return
    if colour_int is not None:
        updates['colour'] = colour_int

    if not updates:
        await interaction.response.send_message("⚠️ You didn't provide any fields to update!", ephemeral=True)
        return

    success = update_artist_bias_db(member.id, **updates)
    if success:
        await interaction.response.send_message(f"Successfully updated the Bias Group entry for {member.mention}!",
                                                ephemeral=True)
    else:
        await interaction.response.send_message(
            f"Update failed. {member.mention} does not have a Bias Group recorded yet.",
            ephemeral=True)

@app_commands.command(name='my-bias-group', description="See who everyone's bias group is!")
@app_commands.describe(member='The member whose bias group you want to see. Leave empty for your own.')
async def bias_group(interaction: discord.Interaction, member: typing.Optional[discord.Member] = None):
    target_user = member or interaction.user
    bias_info = get_artist_bias(target_user.id)

    if not bias_info:
        if member:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, {target_user.display_name} hasn't unlocked a bias group yet!",
                ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, you haven't unlocked a bias group yet!",
                ephemeral=True)
        return

    filename = bias_info['image_filename']
    bias_image = _image_file(filename)
    if bias_image is None:
        # Failsafe just in case the DB has a typo or the image was deleted from Unraid
        await interaction.response.send_message(f"Error: Could not find image file `{filename}` on the server.",
                                                ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{target_user.display_name}'s Bias Group",
        type='rich',
        color=bias_info['colour']
    )
    embed.set_image(url=f"attachment://{filename}")
    embed.add_field(name="", value='\n'.join([
        '**Group Info**',
        f"**Name:** {bias_info['name']}",
        f"**Members:** {bias_info['members']}",
        f"**Label:** {bias_info['label']}",
        f"**Debut Date:** {bias_info['debut_date']}",
        f"\n**{target_user.display_name}'s Favourites**",
        f"**Bias:** {bias_info['bias']}",
        f"**Title Track:** {bias_info['title_track']}",
        f"**B Track:** {bias_info['b_track']}",
        f"**Album:** {bias_info['album']}",
        f"\n**Why {bias_info['name']}?**",
        f"{bias_info['reason']}",
    ]))

    await _send_with_image(interaction, embed, bias_image)
