"""Commands related to the in-server heart currency."""
import logging
import random
import re
import discord
from db.merch import get_user_balance, modify_db_balance

logger = logging.getLogger('iu-bot')

@discord.app_commands.command(name='check-balance',
              description="Check how many hearts you have available to spend.")
async def check_balance(interaction: discord.Interaction):
    """The Discord command logic for checking a user's wallet."""
    restricted = await validate_channel(interaction, 'merch-booth')
    if restricted:
        return

    # Fetch the balance
    try:
        balance = get_user_balance(interaction.user.id)
    except Exception as ex:
        logger.error("Database error occurred: %s", ex)
        await interaction.response.send_message(f"Database error: {ex}", ephemeral=True)
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

@discord.app_commands.command(name='modify-balance', description="[Admin only] Modify a user's heart balance.")
@discord.app_commands.describe(
    member="The server member to modify",
    amount="The number of hearts to add (use negative to subtract)",
    reason="Why this modification is being made (for the audit log)"
)
@discord.app_commands.default_permissions(administrator=True)
async def modify_balance(interaction: discord.Interaction, member: discord.Member, amount: int,
                         reason: str):
    """The Discord command logic for modifying a balance."""
    restricted = await validate_channel(interaction, 'dispatch-news')
    if restricted:
        logger.error("Wrong channel for balance modification command, must be #dispatch-news.")
        return

    # Run the command
    try:
        modify_db_balance(interaction.user.id, member.id, amount, reason)
    except (ValueError, KeyError) as ex:
        await interaction.response.send_message(f"Database error: {ex}", ephemeral=True)
        logger.error("Database error occurred while modifying balance: %s", ex)
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

@discord.app_commands.command(name='random-award',
              description="[Admin] Picks a random user from a list to win hearts!")
@discord.app_commands.describe(
    users="Mention the users to include (e.g., @Alice @Bob @Charlie)",
    amount="The number of hearts to award the winner",
    reason="What this award is for (e.g., Watch Party Attendee)"
)
@discord.app_commands.default_permissions(administrator=True)
async def random_award(interaction: discord.Interaction, users: str, amount: int, reason: str):
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
    raw_ids = re.findall(r'<@!?(\d+)>', users)

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

async def validate_channel(interaction: discord.Interaction, channel: str) -> bool:
    if interaction.channel.name != channel:
        await interaction.response.send_message(
            f"This command can only be used in the #{channel} channel.",
            ephemeral=True
        )
        return True

    return False
