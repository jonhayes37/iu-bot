"""Commands for bias embeds"""
import typing

import discord
from discord import app_commands
from db.biases import (
    create_artist_bias_db, create_ultimate_bias_db, get_artist_bias, get_ultimate_bias,
    update_artist_bias_db, update_ultimate_bias_db
)

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

    # Build the embed using the DB column names
    filename = bias_info['image_filename']
    try:
        bias_image = discord.File(f"iu/media/images/{filename}", filename=filename)
    except FileNotFoundError:
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

    await interaction.response.send_message('', embed=embed, file=bias_image)

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
@app_commands.default_permissions(administrator=True)
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

    # Parse the hex string into an integer for the embed color
    try:
        clean_hex = colour_hex.replace("#", "").replace("0x", "")
        colour_int = int(clean_hex, 16)
    except ValueError:
        await interaction.response.send_message(
            "Invalid hex colour. Please use a format like `ff4980`, `#ff4980`, or `0xff4980`.", 
            ephemeral=True
        )
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
            f"Failed to create entry. {member.mention} likely already has an Ultimate Bias "
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
@app_commands.default_permissions(administrator=True)
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

    # Handle the hex color parsing if it was provided
    if colour_hex is not None:
        try:
            clean_hex = colour_hex.replace("#", "").replace("0x", "")
            updates['colour'] = int(clean_hex, 16)
        except ValueError:
            await interaction.response.send_message(
                "Invalid hex colour. Please use a format like `ff4980`, `#ff4980`, or `0xff4980`.", 
                ephemeral=True
            )
            return

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
@app_commands.default_permissions(administrator=True)
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
    try:
        clean_hex = colour_hex.replace("#", "").replace("0x", "")
        colour_int = int(clean_hex, 16)
    except ValueError:
        await interaction.response.send_message("❌ Invalid hex colour.", ephemeral=True)
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
            f"Failed. {member.mention} likely already has an entry. Use `/update-bias-group`.",
            ephemeral=True)

@app_commands.command(name="update-bias-group",
                      description="[Admin] Update specific fields of an existing bias group record.")
@app_commands.describe(member="The server member whose record you want to update.")
@app_commands.default_permissions(administrator=True)
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

    if colour_hex is not None:
        try:
            clean_hex = colour_hex.replace("#", "").replace("0x", "")
            updates['colour'] = int(clean_hex, 16)
        except ValueError:
            await interaction.response.send_message("❌ Invalid hex colour.", ephemeral=True)
            return

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
    try:
        bias_image = discord.File(f"iu/media/images/{filename}", filename=filename)
    except FileNotFoundError:
        await interaction.response.send_message(
            f"Error: Could not find image file `{filename}` on the server.",
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

    await interaction.response.send_message('', embed=embed, file=bias_image)
