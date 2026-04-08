"""Commands for the End of Year festivities."""
import io
import discord
from db.top_songs import get_all_top_songs
from db.hall_of_fame import get_all_hof_nominations
from ui.eoy_nominations import EOYNominationsHub
from ui.eoy_voting import EOYVotingHub
from utils.end_of_year import get_current_award_year


@discord.app_commands.command(name='end-of-year-nominations',
                              description="[Admin] Posts the End of Year nominations buttons.")
@discord.app_commands.default_permissions(administrator=True)
async def end_of_year_nominations(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    year = get_current_award_year()

    embed = discord.Embed(
        title=f"{year} End of Year Nominations!",
        description=(
            "It's that time of year again! Use the buttons below to submit your ballots at your own pace.\n\n"
            "**1. Top 25 Songs:** Submit your ranked list and 3 honourable mentions.\n"
            "**2. HallyU Hall of Fame:** Nominate the K-Pop legends who deserve to be in our "
            "2026 class of inductees!\n\n"
            "*You can click these buttons as many times as you want to edit your submissions before the deadline!*"
        ),
        color=discord.Color.gold()
    )

    await interaction.channel.send(embed=embed, view=EOYNominationsHub(year))
    await interaction.followup.send("End of Year Hub posted successfully!")


@discord.app_commands.command(name='export-end-of-year-nominations',
                              description="[Admin] Export all End of Year nomination data")
@discord.app_commands.default_permissions(administrator=True)
async def export_eoy_nominations(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    year = get_current_award_year()
    top_songs_data = get_all_top_songs()
    hof_data = get_all_hof_nominations()

    if not top_songs_data and not hof_data:
        await interaction.followup.send(f"No End of Year submissions found for {year} yet!")
        return

    # Initialize our string buffers
    t25_buffer = io.StringIO()
    hms_buffer = io.StringIO()
    hof_buffer = io.StringIO()

    # Process Top 25 and Honorable Mentions
    for sub in top_songs_data:
        username = sub.get('username', 'Unknown User')

        # Write Top 25
        t25_text = sub.get('top_25_clean', '')
        if t25_text:
            t25_buffer.write(f"--- {username} ---\n{t25_text}\n\n")

        # Write Honorable Mentions (Skipping users who left it blank)
        hms_text = sub.get('hms_clean', '')
        if hms_text.strip():
            hms_buffer.write(f"--- {username} ---\n{hms_text}\n\n")

    # Process Hall of Fame
    for sub in hof_data:
        username = sub.get('username', 'Unknown User')
        hof_text = sub.get('nomination_text', '')
        if hof_text:
            hof_buffer.write(f"--- {username} ---\n{hof_text}\n\n")

    # Convert string buffers to Discord File objects
    files = []
    if t25_buffer.getvalue():
        files.append(discord.File(
            fp=io.BytesIO(t25_buffer.getvalue().encode('utf-8')),
            filename=f"top_100_{year}.txt"
        ))

    if hms_buffer.getvalue():
        files.append(discord.File(
            fp=io.BytesIO(hms_buffer.getvalue().encode('utf-8')),
            filename=f"honourable_mentions_{year}.txt"
        ))

    if hof_buffer.getvalue():
        files.append(discord.File(
            fp=io.BytesIO(hof_buffer.getvalue().encode('utf-8')),
            filename=f"hall_of_fame_{year}.txt"
        ))

    await interaction.followup.send(
        content=f"✅ Exported **{len(top_songs_data)}** Top 25 lists and **{len(hof_data)}** "
        f"Hall of Fame ballots for **{year}**!",
        files=files
    )


@discord.app_commands.command(name='end-of-year-voting',
                              description="[Admin] Starts End of Year Voting.")
@discord.app_commands.default_permissions(administrator=True)
async def end_of_year_voting(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    year = get_current_award_year()
    embed = discord.Embed(
        title=f"{year} End of Year Voting is Live!",
        description=(
            "The nominations are in, and it's time to cast your official ballots for the "
            f"**{year} HallyU Music Awards** and the **{year} HallyU Hall of Fame** inductees!\n\n"
            "**Voting is done by a ranked ballot - submit your top 3 choices!**\n"
            "• 🥇 1st Choice = 3 Points\n"
            "• 🥈 2nd Choice = 2 Points\n"
            "• 🥉 3rd Choice = 1 Point\n\n"
            "Click the buttons below to vote. You can change your votes at any time before the deadline!"
        ),
        color=discord.Color.blue()
    )

    await interaction.channel.send(embed=embed, view=EOYVotingHub(year))
    await interaction.followup.send("End of Year Voting posted successfully!")
