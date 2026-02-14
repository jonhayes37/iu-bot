"""merch_admin.py - Admin commands for managing the merch booth and balances."""
import random
import re
import typing
import discord
from db.merch import modify_db_balance, upsert_merch_item


async def admin_modify_balance(interaction: discord.Interaction, member: discord.Member, amount: int, reason: str):
    """The Discord command logic for modifying a balance."""

    # Channel restriction check
    if interaction.channel.name != 'dispatch-news':
        await interaction.response.send_message(
            "This command can only be used in the #dispatch-news channel.", 
            ephemeral=True
        )
        return

    # Run the command
    try:
        modify_db_balance(interaction.user.id, member.id, amount, reason)
    except (ValueError, KeyError) as ex:
        await interaction.response.send_message(f"Database error: {ex}", ephemeral=True)
        return

    # Format the response
    action = "Awarded" if amount >= 0 else "Deducted"
    abs_amount = abs(amount)

    # Send a public embed to the dispatch-news log
    embed = discord.Embed(
        title="Balance Modification",
        color=discord.Color.green() if amount >= 0 else discord.Color.red()
    )
    embed.add_field(name="User", value=member.mention, inline=True)
    embed.add_field(name="Amount", value=f"{action} {abs_amount} heart{'s' if abs_amount != 1 else ''}", inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text=f"Authorized by {interaction.user.display_name}")

    await interaction.response.send_message(embed=embed)


async def admin_random_award(interaction: discord.Interaction, users_input: str, amount: int, reason: str):
    """The Discord command logic for a random giveaway."""

    # Channel restriction check
    if interaction.channel.name != 'dispatch-news':
        await interaction.response.send_message(
            "This command can only be used in the #dispatch-news channel.", 
            ephemeral=True
        )
        return

    # Extract Discord User IDs from the input string using Regex
    # This securely finds the numbers inside standard <@123> or <@!123> mentions
    raw_ids = re.findall(r'<@!?(\d+)>', users_input)

    if not raw_ids:
        await interaction.response.send_message(
            "I couldn't find any valid user mentions. Please make sure to actually @mention the eligible members!", 
            ephemeral=True
        )
        return

    unique_ids = list(set(raw_ids))
    winner_id = int(random.choice(unique_ids))

    try:
        modify_db_balance(interaction.user.id, winner_id, amount, f"Random Award: {reason}")
    except (ValueError, KeyError) as ex:
        await interaction.response.send_message(f"Database error: {ex}", ephemeral=True)
        return

    embed = discord.Embed(
        title="Random Award Winner!",
        color=discord.Color.gold()
    )
    embed.add_field(name="Winner", value=f"<@{winner_id}>", inline=False)
    embed.add_field(name="Prize", value=f"**{amount} hearts!**", inline=True)
    embed.add_field(name="Reason", value=reason, inline=True)
    embed.set_footer(text=f"Rolled by {interaction.user.display_name}")

    await interaction.response.send_message(embed=embed)

async def admin_add_merch(
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


async def admin_set_status(interaction: discord.Interaction, member: discord.Member, status_text: str):
    """Changes the bot's status and logs the user who requested it."""

    if interaction.channel.name != 'dispatch-news':
        await interaction.response.send_message(
            "This command can only be used in the #dispatch-news channel.", 
            ephemeral=True
        )
        return

    # Update the bot's presence
    if status_text == "":
        await interaction.client.change_presence(status=discord.Status.online, activity=None)
    else:
        activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
        await interaction.client.change_presence(status=discord.Status.online, activity=activity)

    # Log the change with the member tagged!
    await interaction.response.send_message(
        f"<@1132749272488624189>'s status has been updated by {member.mention} to `{status_text}`"
    )
