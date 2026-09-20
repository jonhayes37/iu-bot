"""Stand-ins for Discord objects.

They are `MagicMock`s limited to the real discord.py classes (`spec=`), so a test that touches an
attribute discord.py doesn't have fails instead of silently getting a mock back. Anything that
would send something to Discord is an `AsyncMock`, and everything sent is also recorded in order on
`interaction.sent`, so a test can assert on what a user would have seen.
"""

import itertools
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord

_ids = itertools.count(1000)


def next_id() -> int:
    """A unique fake Discord ID."""
    return next(_ids)


@dataclass
class Sent:
    """One thing the bot sent: through the interaction response, a follow-up, or a channel."""
    via: str                      # "response", "followup", "edit", "channel" or "dm"
    content: str | None = None
    kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def ephemeral(self) -> bool:
        """True if only the user who ran the command could see it."""
        return bool(self.kwargs.get("ephemeral", False))

    @property
    def embed(self) -> discord.Embed | None:
        """The first embed, if any."""
        embeds = self.embeds
        return embeds[0] if embeds else None

    @property
    def embeds(self) -> list[discord.Embed]:
        """Every embed sent with the message."""
        if "embeds" in self.kwargs:
            return list(self.kwargs["embeds"])
        return [self.kwargs["embed"]] if self.kwargs.get("embed") else []

    @property
    def text(self) -> str:
        """The content plus every embed's title and description, handy for `in` checks."""
        parts = [self.content or ""]
        for embed in self.embeds:
            parts += [embed.title or "", embed.description or ""]
            parts += [f"{f.name} {f.value}" for f in embed.fields]
        return "\n".join(p for p in parts if p)


def _sent_message() -> MagicMock:
    """What discord.py hands back after sending: a message with an ID that can be edited or deleted."""
    message = MagicMock(spec=discord.Message)
    message.id = next_id()
    message.edit = AsyncMock()
    message.delete = AsyncMock()
    return message


def _recorder(sent: list[Sent], via: str):
    """An AsyncMock side effect that records the call as a Sent and returns a fake sent message."""
    async def record(*args, **kwargs):
        content = args[0] if args else kwargs.pop("content", None)
        kwargs.pop("content", None)
        sent.append(Sent(via, content, kwargs))
        return _sent_message()
    return record


def make_role(name: str, role_id: int | None = None) -> MagicMock:
    """A role with a name (the bot finds and checks roles by name)."""
    role = MagicMock(spec=discord.Role)
    role.id = role_id or next_id()
    role.name = name
    role.mention = f"<@&{role.id}>"
    return role


def make_member(user_id: int | None = None, name: str = "member", *, roles: tuple[str, ...] = (),
                bot: bool = False, administrator: bool = False) -> MagicMock:
    """A guild member. `roles` are role names; `member.send` (a DM) is recorded on `member.sent`."""
    member = MagicMock(spec=discord.Member)
    member.id = user_id or next_id()
    member.name = name
    member.display_name = name
    member.mention = f"<@{member.id}>"
    member.bot = bot
    member.roles = [make_role(role) for role in roles]
    member.guild_permissions = discord.Permissions(administrator=administrator)
    member.sent = []
    member.send = AsyncMock(side_effect=_recorder(member.sent, "dm"))
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    return member


def make_channel(name: str = "general", channel_id: int | None = None) -> MagicMock:
    """A text channel. Whatever is posted with `channel.send` is recorded on `channel.sent`."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id or next_id()
    channel.name = name
    channel.mention = f"<#{channel.id}>"
    channel.sent = []
    channel.send = AsyncMock(side_effect=_recorder(channel.sent, "channel"))
    return channel


def make_guild(*, channels: tuple[str, ...] = (), roles: tuple[str, ...] = (),
               guild_id: int | None = None) -> MagicMock:
    """A server with the named channels and roles, so `discord.utils.get(guild.text_channels, ...)` works."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id or next_id()
    guild.name = "Test Server"
    guild.text_channels = [make_channel(name) for name in channels]
    guild.channels = list(guild.text_channels)
    guild.roles = [make_role(name) for name in roles]
    guild.members = []
    guild.scheduled_events = []
    guild.get_member = MagicMock(side_effect=lambda uid: next((m for m in guild.members if m.id == uid), None))
    guild.get_channel = MagicMock(side_effect=lambda cid: next((c for c in guild.channels if c.id == cid), None))
    return guild


def make_interaction(*, user: MagicMock | None = None, channel: str | MagicMock = "general",
                     guild: MagicMock | None = None, administrator: bool = False) -> MagicMock:
    """
    A slash command / button / modal interaction. Await a command with
    `await command.callback(interaction, ...)`, then read `interaction.sent`.

    `response.is_done()` turns True after the first response or defer, like the real one, and
    `response.defer` records nothing (only messages are recorded).
    """
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = user or make_member(administrator=administrator)
    interaction.channel = channel if isinstance(channel, MagicMock) else make_channel(channel)
    interaction.guild = guild
    interaction.guild_id = guild.id if guild else None
    interaction.permissions = interaction.user.guild_permissions
    interaction.sent = []

    done = {"value": False}

    def _mark_done(recorder):
        async def wrapper(*args, **kwargs):
            done["value"] = True
            await recorder(*args, **kwargs)
        return wrapper

    response = MagicMock(spec=discord.InteractionResponse)
    response.send_message = AsyncMock(side_effect=_mark_done(_recorder(interaction.sent, "response")))
    response.edit_message = AsyncMock(side_effect=_mark_done(_recorder(interaction.sent, "edit")))

    async def _defer(*_, **__):
        done["value"] = True

    response.defer = AsyncMock(side_effect=_defer)
    response.send_modal = AsyncMock(side_effect=_defer)
    response.is_done = MagicMock(side_effect=lambda: done["value"])
    interaction.response = response

    followup = MagicMock(spec=discord.Webhook)
    followup.send = AsyncMock(side_effect=_recorder(interaction.sent, "followup"))
    interaction.followup = followup
    interaction.edit_original_response = AsyncMock(side_effect=_recorder(interaction.sent, "edit"))
    return interaction


def make_message(content: str = "", *, author: MagicMock | None = None, channel: str | MagicMock = "general",
                 guild: MagicMock | None = None) -> MagicMock:
    """A message. `message.reply`, `message.channel.send` and `message.add_reaction` are AsyncMocks."""
    message = MagicMock(spec=discord.Message)
    message.id = next_id()
    message.content = content
    message.author = author or make_member()
    message.channel = channel if isinstance(channel, MagicMock) else make_channel(channel)
    message.guild = guild
    message.sent = []
    message.reply = AsyncMock(side_effect=_recorder(message.sent, "reply"))
    message.add_reaction = AsyncMock()
    message.delete = AsyncMock()
    return message


def make_client(*, guild: MagicMock | None = None) -> MagicMock:
    """A stand-in for the running bot (`IUBot`) as tasks and triggers see it."""
    client = MagicMock(spec=discord.Client)
    client.user = make_member(name="IU", bot=True)
    client.guilds = [guild] if guild else []
    client.get_guild = MagicMock(side_effect=lambda gid: guild if guild and guild.id == gid else None)
    client.cached_messages = []
    client.fetch_user = AsyncMock()
    client.get_user = MagicMock(return_value=None)
    return client
