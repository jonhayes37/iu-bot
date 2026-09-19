"""Docstring for iu.commands.merch_user"""
import logging
import random
import typing

import discord

from config import Channel, EMOJI_WOOYEON_SHOCK, admin_user_id
from commands.hearts import validate_channel
from db.merch import (
    get_user_balance, get_user_inventory, get_user_merch_catalog,
    process_purchase, upsert_merch_item, get_all_item_owners, reset_item_inventory
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

    restricted = await validate_channel(interaction, Channel.DISPATCH_NEWS)
    if restricted:
        return

    # Basic validation
    if price <= 0:
        await interaction.response.send_message("Price cannot be free!", ephemeral=True)
        return

    upsert_merch_item(item_id, name, description, price, max_per_user)

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

    restricted = await validate_channel(interaction, Channel.MERCH_BOOTH)
    if restricted:
        return

    balance = get_user_balance(interaction.user.id)
    items = get_user_merch_catalog(interaction.user.id)

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

    restricted = await validate_channel(interaction, Channel.MERCH_BOOTH)
    if restricted:
        return

    # Execute the database logic
    success, message = process_purchase(interaction.user.id, item_id)

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
        dispatch_channel = discord.utils.get(interaction.guild.text_channels, name=Channel.DISPATCH_NEWS)
        if dispatch_channel:
            # Fetch the item name from the DB message to keep the log detailed
            await dispatch_channel.send(
                f"<@{interaction.user.id}> {message} <@{admin_user_id()}> will help with redemption."
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

    restricted = await validate_channel(interaction, Channel.MERCH_BOOTH)
    if restricted:
        return

    # Fetch the data
    inventory = get_user_inventory(interaction.user.id)

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

@discord.app_commands.command(
        name='draw-raffle',
        description="[Admin] Draw a random winner from all RAFFLE ticket holders and reset the pool.")
@discord.app_commands.default_permissions(administrator=True)
async def draw_raffle(interaction: discord.Interaction):
    """The Discord command logic for drawing a raffle winner."""

    # Restrict to dispatch-news like the other admin commands
    restricted = await validate_channel(interaction, Channel.DISPATCH_NEWS)
    if restricted:
        return

    # Fetch all tickets
    ticket_data = get_all_item_owners('RAFFLE')
    if not ticket_data:
        await interaction.response.send_message("Nobody has bought any raffle tickets yet!", ephemeral=True)
        return

    # Create parallel lists for weighted random selection
    user_ids = [user_id for user_id, _ in ticket_data]
    weights = [quantity for _, quantity in ticket_data]
    total_tickets = sum(weights)

    # Pick a winner
    # The `k=1` parameter returns a list with one item, so we select it.
    if not user_ids: # Should be caught by the ticket_data check, but for safety
        await interaction.response.send_message("Raffle pool is empty.", ephemeral=True)
        return
    winner_id = random.choices(user_ids, weights=weights, k=1)[0]
    logger.info("Raffle winner: %s", winner_id)

    # Wipe the inventories for RAFFLE so everyone is back to 0
    reset_item_inventory('RAFFLE')

    # Announce the winner
    embed = discord.Embed(
        title="🎟️ Raffle Winner!",
        description=(
            f"Congratulations <@{winner_id}>! You've won the raffle!\n\n"
            f"**You get an album of your choice from the end of year top 100** "
            f"{EMOJI_WOOYEON_SHOCK} "
            f"Please DM <@{admin_user_id()}> with your choice!"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Winner drawn from a pool of {total_tickets} tickets.")

    # We put the mention in the message content so Discord actually pings them,
    # as mentions inside embeds do not trigger push notifications.
    await interaction.response.send_message(
        content=f"<@{winner_id}>",
        embed=embed
    )
