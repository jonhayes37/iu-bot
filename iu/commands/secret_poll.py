"""Commands for secret polls: votes nobody sees, with the results sent only to the admin."""
from datetime import datetime, timedelta, timezone

import discord
from db.bot import (
    create_secret_poll, delete_secret_poll, get_recent_secret_polls, get_secret_poll, get_secret_poll_counts,
    set_secret_poll_message
)
from ui.secret_poll import SecretPollView, poll_embed, results_text
from utils.validation import admin_only

# A message holds at most 25 buttons, and a button shows at most 80 characters
MAX_OPTIONS = 25
MAX_OPTION_LENGTH = 80
MAX_TITLE_LENGTH = 200
MAX_HOURS = 168


def _options_problem(options: list[str]) -> str | None:
    """Why these options can't be a poll, or None if they can."""
    if len(options) < 2:
        return "❌ A poll needs at least 2 options, separated by `|`."
    if len(options) > MAX_OPTIONS:
        return f"❌ A poll can have at most {MAX_OPTIONS} options (one button each); you gave {len(options)}."
    too_long = [option for option in options if len(option) > MAX_OPTION_LENGTH]
    if too_long:
        return (f"❌ A button shows at most {MAX_OPTION_LENGTH} characters, and this option is longer: "
                f"{too_long[0][:MAX_OPTION_LENGTH]}…")
    if len({option.casefold() for option in options}) < len(options):
        return "❌ The same option appears more than once."
    return None


@discord.app_commands.command(name='secret-poll',
                              description="[Admin] Post a poll whose results are only sent to you.")
@discord.app_commands.describe(
    title="What the poll is about (e.g. 'Song of the Year tiebreaker')",
    options="The choices, separated by | (e.g. 'IVE - HEYA | aespa - Supernova')",
    hours="How long voting stays open, in hours (24 by default)"
)
@admin_only
async def secret_poll(interaction: discord.Interaction,
                      title: discord.app_commands.Range[str, 1, MAX_TITLE_LENGTH],
                      options: str,
                      hours: discord.app_commands.Range[int, 1, MAX_HOURS] = 24):
    labels = [option.strip() for option in options.split('|') if option.strip()]
    problem = _options_problem(labels)
    if problem:
        await interaction.response.send_message(problem, ephemeral=True)
        return

    # Posting the poll is a Discord API call
    await interaction.response.defer(ephemeral=True)
    closes_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0)
    poll_id = create_secret_poll(title.strip(), labels, interaction.user.id, interaction.channel.id, closes_at)
    try:
        message = await interaction.channel.send(embed=poll_embed(title.strip(), closes_at),
                                                 view=SecretPollView(poll_id, labels))
    except discord.HTTPException:
        # Nothing was posted, so don't leave a poll behind that would close and send empty results
        delete_secret_poll(poll_id)
        raise
    set_secret_poll_message(poll_id, message.id)

    await interaction.followup.send(
        f"✅ Secret poll #{poll_id} posted. It closes {discord.utils.format_dt(closes_at, 'f')}, and I'll DM "
        "you the results then. Nobody else sees them. `/secret-poll-results` shows them to you any time.")


async def _poll_autocomplete(_: discord.Interaction, current: str):
    """Suggests the newest polls whose title or number contains what the admin has typed."""
    typed = current.casefold()
    polls = [poll for poll in get_recent_secret_polls()
             if typed in poll.title.casefold() or typed in str(poll.poll_id)]
    return [discord.app_commands.Choice(
        name=f"#{poll.poll_id} {poll.title} ({'closed' if poll.closed else 'open'})"[:100], value=poll.poll_id)
        for poll in polls]


@discord.app_commands.command(name='secret-poll-results',
                              description="[Admin] Privately show the results of a secret poll.")
@discord.app_commands.describe(poll="The poll (start typing its title)")
@discord.app_commands.autocomplete(poll=_poll_autocomplete)
@admin_only
async def secret_poll_results(interaction: discord.Interaction, poll: int):
    found = get_secret_poll(poll)
    if found is None:
        await interaction.response.send_message(f"❌ There is no secret poll #{poll}.", ephemeral=True)
        return
    await interaction.response.send_message(results_text(found, get_secret_poll_counts(poll)), ephemeral=True)
