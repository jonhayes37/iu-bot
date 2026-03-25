"""Docstring for iu.commands.merch_user"""
import logging
import typing

import discord

from commands.hearts import validate_channel
from db.merch import (
    get_user_balance, get_user_inventory, get_user_merch_catalog,
    process_purchase, upsert_merch_item
)

logger = logging.getLogger('iu-bot')

@discord.app_commands.command(name='add-merch', description="[Admin] Add or update an item in the Merch Booth.")
@discord.app_commands.describe(
    item_id="A short, unique code (e.g., CUSTEMOJI)",
    name="The display name of the perk",
    description="What the user actually gets",
    price="Cost in hearts",
    max_per_user="Optional: Maximum times a single user can buy this"
)
@discord.app_commands.default_permissions(administrator=True)
async def add_merch(
    interaction: discord.Interaction,
    item_id: str,
    name: str,
    description: str,
    price: int,
    max_per_user: typing.Optional[int]
):
    """The Discord command logic for adding/updating merch items."""

    if interaction.channel.name != 'dispatch-news':
        await interaction.response.send_message(
            "This command can only be used in the #dispatch-news channel.", 
            ephemeral=True
        )
        return

    # Basic validation
    if price <= 0:
        await interaction.response.send_message("Price cannot be free!", ephemeral=True)
        return

    try:
        upsert_merch_item(item_id, name, description, price, max_per_user)
    except (ValueError, KeyError) as ex:
        await interaction.response.send_message(f"Database error: {ex}", ephemeral=True)
        return

    # Format the confirmation
    limit_text = f"{max_per_user} per user" if max_per_user else "Unlimited"

    embed = discord.Embed(
        title="🛒 Merch Booth Updated!",
        color=discord.Color.purple()
    )
    embed.add_field(name="SKU", value=f"`{item_id.upper()}`", inline=False)
    embed.add_field(name="Name", value=name, inline=True)
    embed.add_field(name="Price", value=f"{price} hearts", inline=True)
    embed.add_field(name="Stock Limit", value=limit_text, inline=True)
    embed.add_field(name="Description", value=description, inline=False)

    await interaction.response.send_message(embed=embed)

@discord.app_commands.command(name='view-merch', description="Browse the available perks in the merch stand!")
async def view_merch(interaction: discord.Interaction):
    """The Discord command logic for displaying the personalized merch booth."""

    restricted = await validate_channel(interaction, 'merch-booth')
    if restricted:
        return

    try:
        balance = get_user_balance(interaction.user.id)
        items = get_user_merch_catalog(interaction.user.id)
    except Exception as ex:
        await interaction.response.send_message(f"Database error: {ex}", ephemeral=True)
        return

    if not items:
        await interaction.response.send_message(
            "The merch booth is currently empty! Tell the admins to stock the shelves.", 
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="🛍️ The Merch Booth",
        description=f"You currently have **{balance} hearts**.\nUse `/purchase <item_id>` to buy a perk!",
        color=discord.Color(0xff4980)
    )
    embed = _add_items_to_embed(embed, items)

    await interaction.response.send_message(embed=embed)

@discord.app_commands.command(name='purchase', description="Buy something from the merch booth!")
@discord.app_commands.describe(
    item_id="The short code of the item you want to buy (e.g., CUSTEMOJI)")
async def purchase(interaction: discord.Interaction, item_id: str):
    """The Discord command logic for buying an item."""

    restricted = await validate_channel(interaction, 'merch-booth')
    if restricted:
        return

    # Execute the database logic
    try:
        success, message = process_purchase(interaction.user.id, item_id)
    except Exception as ex:
        await interaction.response.send_message(f"Database error: {ex}", ephemeral=True)
        return

    # Format the response based on success or failure
    if success:
        embed = discord.Embed(
            title="🎉 Purchase Successful!",
            description=message,
            color=discord.Color.green()
        )
        # Send publicly so the server can celebrate the purchase
        await interaction.response.send_message(embed=embed)

        # Send the log in #dispatch-news
        dispatch_channel = discord.utils.get(interaction.guild.text_channels, name='dispatch-news')
        if dispatch_channel:
            # Fetch the item name from the DB message to keep the log detailed
            await dispatch_channel.send(
                f"<@{interaction.user.id}> {message} <@904751089633615972> will help with redemption."
            )
    else:
        embed = discord.Embed(
            title="❌ Purchase Failed",
            description=message,
            color=discord.Color.red()
        )
        # Send ephemerally so errors don't clutter the chat
        await interaction.response.send_message(embed=embed, ephemeral=True)

@discord.app_commands.command(name='purchase-history', description="View all of the merch you've bought!")
async def purchase_history(interaction: discord.Interaction):
    """The Discord command logic for viewing owned perks."""

    restricted = await validate_channel(interaction, 'merch-booth')
    if restricted:
        return

    # Fetch the data
    try:
        inventory = get_user_inventory(interaction.user.id)
    except Exception as ex:
        await interaction.response.send_message(f"Database error: {ex}", ephemeral=True)
        return

    # Handle the empty state
    if not inventory:
        await interaction.response.send_message(
            "You haven't bought anything yet! Use `/view-merch` to see what's available.", 
            ephemeral=True
        )
        return

    # Format the backpack embed
    embed = discord.Embed(
        title="Your Purchase History",
        description="Here is everything you've collected so far:",
        color=discord.Color(0xff4980)
    )

    # Loop through their owned items
    for name, item_id, description, quantity in inventory:
        quantity_text = f"Owned: **{quantity}**"
        embed.add_field(
            name=f"{name} (`{item_id}`)",
            value=f"{description}\n*{quantity_text}*",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

def _add_items_to_embed(embed, items):
    # Separate the items into two lists
    available_items = []
    sold_out_items = []

    for item in items:
        # Unpack the tuple
        item_id, name, description, price, max_per_user, quantity_owned = item

        # Determine if it's sold out for this specific user
        if max_per_user is not None and quantity_owned >= max_per_user:
            sold_out_items.append(item)
        else:
            available_items.append(item)

    # Add Available Items First (Prices Descending)
    for item_id, name, description, price, max_per_user, quantity_owned in available_items:
        remaining = max_per_user - quantity_owned if max_per_user else None
        limit_text = f"**{remaining}** available" if remaining else "Unlimited stock"

        embed.add_field(
            name=f"[{price} hearts] **{name}** (`{item_id}`)",
            value=f"{description}\n*{limit_text}*",
            inline=False
        )

    # Add Sold Out Items Last (No cost shown)
    for item_id, name, description, price, max_per_user, quantity_owned in sold_out_items:
        embed.add_field(
            name=f"~~{name} (`{item_id}`)~~ - **SOLD OUT**",
            value=description,
            inline=False
        )

    return embed
