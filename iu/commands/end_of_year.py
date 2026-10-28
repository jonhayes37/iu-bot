"""Commands for the End of Year festivities."""
import io
import logging
import discord
from db.bot import EndOfYearPost, EndOfYearPostKind, close_end_of_year, get_end_of_year_posts
from db.hall_of_fame import get_all_hof_nominations, get_hof_ballots
from db.hmas import get_active_hma_categories, get_hma_ballots
from db.top_songs import get_all_top_songs
from ui.end_of_year import post_hub
from ui.eoy_nominations import EOYNominationsHub
from ui.eoy_voting import EOYVotingHub
from ui.hma_suggestions import HMASuggestionsHub
from utils.ballots import count_ballots, rank_tallies, tied_for_first
from utils.discord_files import text_file
from utils.end_of_year import get_festivities_year
from utils.validation import admin_only

logger = logging.getLogger('iu-bot')

# How many places the results list for each category
RESULTS_PLACES = 5

# The hub each kind of post shows, so /end-of-year-close can redraw it with its buttons greyed out
HUBS = {
    EndOfYearPostKind.SUGGESTIONS: HMASuggestionsHub,
    EndOfYearPostKind.NOMINATIONS: EOYNominationsHub,
    EndOfYearPostKind.VOTING: EOYVotingHub,
}


@discord.app_commands.command(name='end-of-year-nominations',
                              description="[Admin] Posts the End of Year nominations buttons.")
@admin_only
async def end_of_year_nominations(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    year = get_festivities_year()

    embed = discord.Embed(
        title=f"{year} End of Year Nominations!",
        description=(
            "It's that time of year again! Use the buttons below to submit your ballots at your own pace.\n\n"
            "**1. Top 25 Songs:** Submit your ranked list and 3 honourable mentions.\n"
            "**2. HallyU Hall of Fame:** Nominate the K-Pop legends who deserve to be in our "
            f"{year} class of inductees!\n\n"
            "*You can click these buttons as many times as you want to edit your submissions before the deadline!*"
        ),
        color=discord.Color.gold()
    )

    if await post_hub(interaction, year, EndOfYearPostKind.NOMINATIONS, embed, EOYNominationsHub(year)):
        await interaction.followup.send("End of Year Hub posted successfully!")


@discord.app_commands.command(name='export-end-of-year-nominations',
                              description="[Admin] Export all End of Year nomination data")
@admin_only
async def export_eoy_nominations(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    year = get_festivities_year()
    top_songs_data = get_all_top_songs(year)
    hof_data = get_all_hof_nominations(year)

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
            filename=f"top_25_{year}.txt"
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
@admin_only
async def end_of_year_voting(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    year = get_festivities_year()
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

    if await post_hub(interaction, year, EndOfYearPostKind.VOTING, embed, EOYVotingHub(year)):
        await interaction.followup.send("End of Year Voting posted successfully!")


def _results_section(title: str, ballots: list[tuple[str, str, str]]) -> tuple[list[str], list[str]]:
    """One category's lines for the results file, and the nominees tied for 1st on every count (if any)."""
    lines = [f"### {title} ({len(ballots)} {'ballot' if len(ballots) == 1 else 'ballots'}) ###"]
    if not ballots:
        return lines + ["No votes.", ""], []

    placings = rank_tallies(count_ballots(ballots))
    for placing in placings:
        if placing.rank > RESULTS_PLACES:
            break
        tally = placing.tally
        rank = f"T{placing.rank}" if placing.tied else str(placing.rank)
        lines.append(f"{rank}. {tally.nominee}: {tally.points} points "
                     f"(1st: {tally.firsts}, 2nd: {tally.seconds}, 3rd: {tally.thirds})")

    tied = tied_for_first(placings)
    if tied:
        lines.append(f"⚠️ TIED FOR 1ST on every count: {', '.join(tied)}. Needs a tiebreaker.")
    return lines + [""], tied


@discord.app_commands.command(name='end-of-year-results',
                              description="[Admin] Export the top 5 in every HMA category and the Hall of Fame.")
@discord.app_commands.describe(year="The award year to count (defaults to this year's festivities)")
@admin_only
async def end_of_year_results(interaction: discord.Interaction, year: int = None):
    await interaction.response.defer(ephemeral=True)
    year = year or get_festivities_year()

    hof_ballots = get_hof_ballots(year)
    hma_ballots = get_hma_ballots(year)
    categories = get_active_hma_categories()
    if not hof_ballots and not any(hma_ballots.get(c['category_id']) for c in categories):
        await interaction.followup.send(f"No votes found for {year} yet.")
        return

    body = []
    ties = []

    lines, tied = _results_section("HallyU Hall of Fame", hof_ballots)
    body += ["████ HALL OF FAME ████", ""] + lines
    if tied:
        ties.append(("HallyU Hall of Fame", tied))

    family = None
    for category in categories:
        if category['family'] != family:
            family = category['family']
            body += [f"████ {family.upper()} ████", ""]
        lines, tied = _results_section(category['name'], hma_ballots.get(category['category_id'], []))
        body += lines
        if tied:
            ties.append((category['name'], tied))

    header = [
        f"🏆 {year} End of Year Results 🏆", "=" * 50,
        "Points: 1st choice = 3, 2nd = 2, 3rd = 1. Ties are broken by the most 1st choices, then 2nd, then 3rd.",
        f"The top {RESULTS_PLACES} of each category. T marks nominees level on every count.", "",
    ]
    if ties:
        header += ["⚠️ NEEDS A TIEBREAKER (tied for 1st on every count):"]
        header += [f"- {title}: {', '.join(names)}" for title, names in ties]
    else:
        header += ["✅ Every 1st place is decided."]
    header += ["", "=" * 50, ""]

    summary = f"✅ Here are the **{year}** results."
    if ties:
        summary += f"\n⚠️ Tied for 1st on every count: {', '.join(title for title, _ in ties)}."
    await interaction.followup.send(
        summary, file=text_file("\n".join(header + body), f"{year}_end_of_year_results.txt"))


async def _close_post(interaction: discord.Interaction, year: int, post: EndOfYearPost) -> str:
    """Greys out one post's buttons. Returns 'closed', 'gone' (the post or its channel was deleted) or 'failed'."""
    channel = interaction.guild.get_channel(post.channel_id) if interaction.guild else None
    if channel is None:
        return "gone"
    try:
        message = await channel.fetch_message(post.message_id)
        await message.edit(view=HUBS[post.kind](year, closed=True))
    except discord.NotFound:
        return "gone"
    except discord.HTTPException as ex:
        logger.warning("Could not close end of year post %s: %s", post.message_id, ex)
        return "failed"
    return "closed"


@discord.app_commands.command(name='end-of-year-close',
                              description="[Admin] Close this year's end of year posts once final voting has ended.")
@admin_only
async def end_of_year_close(interaction: discord.Interaction):
    # Editing each post is a Discord API call or two
    await interaction.response.defer(ephemeral=True)
    year = get_festivities_year()

    newly_closed = close_end_of_year(year)
    outcomes = [await _close_post(interaction, year, post) for post in get_end_of_year_posts(year)]

    lines = [
        f"🔒 The **{year}** end of year festivities are closed." if newly_closed
        else f"🔒 The **{year}** end of year festivities were already closed.",
        "Anyone who presses an old button, sends a form or runs `/hma-nomination` is told they're closed.",
        f"Buttons greyed out on **{outcomes.count('closed')}** "
        f"{'post' if outcomes.count('closed') == 1 else 'posts'}.",
    ]
    if outcomes.count("gone"):
        lines.append(f"{outcomes.count('gone')} had already been deleted.")
    if outcomes.count("failed"):
        lines.append(f"⚠️ {outcomes.count('failed')} couldn't be edited (check IU can still see that channel). "
                     "Their buttons refuse anyway.")
    lines.append("Run `/end-of-year-results` for the winners.")
    await interaction.followup.send("\n".join(lines))
