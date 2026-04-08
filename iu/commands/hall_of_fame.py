"""Commands for the hall of fame"""
import discord
from db.hall_of_fame import set_hof_final_nominees

@discord.app_commands.command(name='hall-of-fame-set-nominees',
                              description="[Admin] Set the shortlist of nominees for the Hall of Fame.")
@discord.app_commands.describe(
    nominees_pipe="Pipe-separated list of nominees (e.g., 'BTS | Girls Generation | Seventeen')"
)
@discord.app_commands.default_permissions(administrator=True)
async def hall_of_fame_set_nominees(interaction: discord.Interaction, nominees_pipe: str):
    await interaction.response.defer(ephemeral=True)

    # Split by the pipe character and strip whitespace
    nominees = [n.strip() for n in nominees_pipe.split('|') if n.strip()]
    if not nominees:
        await interaction.followup.send("❌ No valid nominees found. Check your formatting.")
        return

    try:
        year = set_hof_final_nominees(nominees)
        formatted_list = "\n".join([f"• {name}" for name in nominees])
        await interaction.followup.send(
            f"✅ **Saved {len(nominees)} Hall of Fame nominees for {year}!**\n\n{formatted_list}"
        )

    except Exception as e:
        await interaction.followup.send(f"❌ Database error: {e}")
