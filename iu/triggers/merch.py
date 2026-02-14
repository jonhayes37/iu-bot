import discord

from db.merch import process_daily_heart, process_milestone_award
from iu.main import DB_PATH_MERCH
import sqlite3

# Handle emoji reactions
async def handle_reaction_add(payload, client):
    if payload.member and payload.member.bot:
        return

    channel = client.get_channel(payload.channel_id)
    if not channel:
        return
        
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return 

    dispatch_channel = discord.utils.get(message.guild.text_channels, name='dispatch-news')

    # ================= 
    # Daily Heart Award
    # =================
    if payload.emoji.name == "aGiveHeart":
        sender_id = payload.user_id
        receiver_id = message.author.id

        if sender_id != receiver_id:
            if process_daily_heart(sender_id, receiver_id, message.jump_url) and dispatch_channel:
                await dispatch_channel.send(
                    f"<@{sender_id}> gave <@{receiver_id}> their daily heart on {message.jump_url}!"
                )

    # ==========================================
    # FEATURE 2: 5-Reaction Milestone (IU-8)
    # ==========================================
    
    total_reactions = sum(r.count for r in message.reactions)
    if total_reactions >= 5:
        
        # Check if already paid
        with sqlite3.connect(DB_PATH_MERCH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT paid_out FROM milestone_messages WHERE message_id = ?", (message.id,))
            if cursor.fetchone():
                return
                
        # Count unique users across all emojis
        unique_users = set()
        for reaction in message.reactions:
            async for user in reaction.users():
                if not user.bot:
                    unique_users.add(user.id)
                    
        # Process payout
        if len(unique_users) >= 5:
            if process_milestone_award(message.id, message.author.id, message.jump_url) and dispatch_channel:
                await dispatch_channel.send(
                    f"<@{message.author.id}>'s [post]({message.jump_url}) got reactions from 5 people, and earned 3 hearts!"
                )
