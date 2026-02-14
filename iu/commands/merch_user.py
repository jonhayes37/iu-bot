# commands/economy_user.py
import discord
from db.merch import get_user_balance, get_user_merch_catalog, process_purchase, get_user_inventory

async def user_check_balance(interaction: discord.Interaction):
    """The Discord command logic for checking a user's wallet."""
    
    # Channel restriction check
    if interaction.channel.name != 'merch-booth':
        await interaction.response.send_message(
            "This command can only be used in the #merch-booth channel.", 
            ephemeral=True
        )
        return

    # Fetch the balance
    try:
        balance = get_user_balance(interaction.user.id)
    except Exception as e:
        await interaction.response.send_message(f"Database error: {e}", ephemeral=True)
        return

    # Format the response
    embed = discord.Embed(
        title="🎫 Your Wallet",
        description=f"You currently have **{balance} heart{'s' if balance != 1 else ''}** available to spend.",
        color=discord.Color(0xFF4980)
    )
    
    # Add a helpful footer for user navigation
    embed.set_footer(text="Use /view-merch to see what you can buy!")

    # We send this publicly in the channel so others can see!
    await interaction.response.send_message(embed=embed)


async def user_view_merch(interaction: discord.Interaction):
    """The Discord command logic for displaying the personalized merch booth."""
    
    if interaction.channel.name != 'merch-booth':
        await interaction.response.send_message(
            "This command can only be used in the #merch-booth channel.", 
            ephemeral=True
        )
        return

    try:
        user_id = interaction.user.id
        balance = get_user_balance(user_id)
        items = get_user_merch_catalog(user_id)
    except Exception as e:
        await interaction.response.send_message(f"Database error: {e}", ephemeral=True)
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
        color=discord.Color(0xff66cc) 
    )

    # 1. Separate the items into two lists
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
        title = f"[{price} hearts] **{name}** (`{item_id}`)**"
        
        embed.add_field(
            name=title,
            value=f"{description}\n*{limit_text}*",
            inline=False
        )

    # Add Sold Out Items Last (No cost shown)
    for item_id, name, description, price, max_per_user, quantity_owned in sold_out_items:
        title = f"~~{name} (`{item_id}`)~~ - **SOLD OUT**"
        
        embed.add_field(
            name=title,
            value=description,
            inline=False
        )

    await interaction.response.send_message(embed=embed)


async def user_purchase_merch(interaction: discord.Interaction, item_id: str):
    """The Discord command logic for buying an item."""
    
    # Enforce the merch-booth channel
    if interaction.channel.name != 'merch-booth':
        await interaction.response.send_message(
            "This command can only be used in the #merch-booth channel.", 
            ephemeral=True
        )
        return

    # Execute the database logic
    try:
        success, message = process_purchase(interaction.user.id, item_id)
    except Exception as e:
        await interaction.response.send_message(f"Database error: {e}", ephemeral=True)
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


async def user_purchase_history(interaction: discord.Interaction):
    """The Discord command logic for viewing owned perks."""
    
    # Enforce the merch-booth channel
    if interaction.channel.name != 'merch-booth':
        await interaction.response.send_message(
            "This command can only be used in the #merch-booth channel.", 
            ephemeral=True
        )
        return

    # Fetch the data
    try:
        inventory = get_user_inventory(interaction.user.id)
    except Exception as e:
        await interaction.response.send_message(f"Database error: {e}", ephemeral=True)
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