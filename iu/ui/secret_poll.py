"""Secret polls: a button per option, private confirmations, and results only the poll's admin sees."""

from datetime import datetime, timezone

import discord

from db.bot import SecretPoll, SecretVoteResult, get_secret_poll_options, record_secret_vote
from ui.base import reports_errors

CLOSED_TEXT = "Voting has closed."


def poll_embed(title: str, closes_at: datetime, closed: bool = False) -> discord.Embed:
    """The public post. It never shows a count, and once closed it only says so."""
    if closed:
        description = CLOSED_TEXT
    else:
        description = (
            "Press a button to vote. Your vote is secret, and you can change it until voting closes "
            f"{discord.utils.format_dt(closes_at, 'R')} ({discord.utils.format_dt(closes_at, 'f')})."
        )
    return discord.Embed(title=f"🗳️ {title}", description=description, color=discord.Color.purple())


def results_text(poll: SecretPoll, counts: list[tuple[str, int]]) -> str:
    """The results, for the admin only: votes per option, most first, and the winner or a tie."""
    status = "closed" if poll.closed else f"closes {discord.utils.format_dt(poll.closes_at, 'R')}"
    total = sum(votes for _, votes in counts)
    lines = [f"🗳️ **{poll.title}** (secret poll #{poll.poll_id}, {status})",
             f"{total} {'vote' if total == 1 else 'votes'}"]
    if not total:
        return "\n".join(lines + ["Nobody has voted."])

    ranked = sorted(counts, key=lambda count: -count[1])          # sorted() keeps the given order for ties
    lines += [f"• {label}: {votes}" for label, votes in ranked]
    leaders = [label for label, votes in ranked if votes == ranked[0][1]]
    if len(leaders) > 1:
        lines.append(f"⚠️ Tied: {', '.join(leaders)}")
    else:
        lines.append(f"🏆 {'Winner' if poll.closed else 'Leading'}: {leaders[0]}")
    return "\n".join(lines)


class SecretVoteButton(discord.ui.DynamicItem[discord.ui.Button],
                       template=r"secret_poll:(?P<poll_id>\d+):(?P<position>\d+)"):
    """
    One option of a secret poll. The poll and option are part of the button's ID, so polls keep
    working after a restart.
    """

    def __init__(self, poll_id: int, position: int, label: str = "Vote", disabled: bool = False):
        super().__init__(discord.ui.Button(
            label=label, style=discord.ButtonStyle.primary, disabled=disabled,
            custom_id=f"secret_poll:{poll_id}:{position}"))
        self.poll_id = poll_id
        self.position = position

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item, match, /):
        return cls(int(match["poll_id"]), int(match["position"]))

    @reports_errors
    async def callback(self, interaction: discord.Interaction):
        result = record_secret_vote(self.poll_id, interaction.user.id, self.position, datetime.now(timezone.utc))
        if result is SecretVoteResult.CLOSED:
            text = f"🔒 {CLOSED_TEXT}"
        elif result is SecretVoteResult.NO_SUCH_OPTION:
            text = "❌ That option isn't part of this poll any more."
        else:
            label = get_secret_poll_options(self.poll_id)[self.position]
            text = (f"🗳️ You voted for **{label}**. Your vote is secret. "
                    "Press another button to change it before voting closes.")
        await interaction.response.send_message(text, ephemeral=True)


class SecretPollView(discord.ui.View):
    """The poll's buttons, one per option. `closed` greys them out."""

    def __init__(self, poll_id: int, options: list[str], closed: bool = False):
        super().__init__(timeout=None)
        for position, label in enumerate(options):
            self.add_item(SecretVoteButton(poll_id, position, label, disabled=closed))
