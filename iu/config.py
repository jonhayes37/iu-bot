"""Central configuration for the bot.

Everything that is specific to the deployment or to the HallyU server lives here: environment
variables, file locations, the names of the channels and roles the bot looks up, and the Discord
IDs it refers to. Change a name or ID here once instead of hunting for it across the code.

Environment variables are read when asked for, not when this module is imported, so tests can
change them with monkeypatch.setenv.
"""

import enum
import os
import tempfile
from pathlib import Path

IU_DIR = Path(__file__).resolve().parent
MEDIA_DIR = IU_DIR / 'media'
SCHEMA_DIR = IU_DIR / 'db' / 'schema'


class Database(enum.Enum):
    """The bot's SQLite databases. The value is the schema file name (without .sql)."""
    BIASES = 'biases'
    BOT = 'bot'
    HALL_OF_FAME = 'hall_of_fame'
    HMAS = 'hmas'
    LISTEN_GAME = 'listen_game'
    LISTS = 'lists'
    MERCH = 'merch'
    RELEASES = 'releases'
    ROLES = 'roles'
    TOP_SONGS = 'top_songs'
    TOURNAMENTS = 'tournaments'

    @property
    def env_var(self) -> str:
        """The environment variable holding this database's file path, e.g. DB_PATH_MERCH."""
        return f"DB_PATH_{self.name}"

    @property
    def path(self) -> str | None:
        """The database file path from the environment, or None if it isn't set."""
        return os.getenv(self.env_var)

    @property
    def schema_path(self) -> Path:
        """The .sql file that creates this database's tables."""
        return SCHEMA_DIR / f"{self.value}.sql"


class Channel(enum.StrEnum):
    """Names of the server channels the bot looks up."""
    COMMUNITY = 'community'
    COMMUNITY_EVENTS = 'community-events'
    DISPATCH_NEWS = 'dispatch-news'
    INTRODUCTIONS = 'introductions'
    LISTEN_GAME = 'listen-game'
    MERCH_BOOTH = 'merch-booth'
    NEW_RELEASES = 'new-releases'
    ROLES = 'roles'
    RULES = 'rules'
    SANDBOX = 'sandbox'
    TOURNAMENTS = 'tournaments'
    WELCOME = 'welcome'


class Role(enum.StrEnum):
    """Names of the server roles the bot looks up or checks."""
    LISTEN_GAME_GM = 'Listen Game GM'
    LISTEN_GAME_PLAYER = 'Listen Game Player'
    TRAINEE = 'Trainee'
    WATCH_PARTIES = 'Watch Parties'


# Server-specific Discord IDs, custom emoji and links
DEFAULT_ADMIN_USER_ID = 904751089633615972
UHM_JUNG_HWA_FAN_USER_ID = 330890965881585665
GUILD_URL = "https://discord.com/channels/795846406187384842"
ROLES_HOWTO_URL = f"{GUILD_URL}/838498988566642708/1066953623667482665"
HEART_ECONOMY_URL = f"{GUILD_URL}/795855921020010496/1472346872147476551"

EMOJI_BLACKPINK = "<:blackpink:795873701177589761>"
EMOJI_GIVE_HEART = "<a:aGiveHeart:1472262590477500569>"
EMOJI_HALLYU = "<:hallyu:795848873910206544>"
EMOJI_IU = "<:iu:802970899174129744>"
EMOJI_IU_PRAY = "<:iuPray:1456031268494905428>"
EMOJI_WOOYEON_SHOCK = "<a:aWooyeonShock:865829919136677888>"

# Names of the custom emoji that count as giving a daily heart
HEART_EMOJI_NAMES = ("aGiveHeart", "giveHeart")


def discord_token() -> str | None:
    """The bot token (DISCORD_TOKEN)."""
    return os.getenv('DISCORD_TOKEN')


def log_level() -> str:
    """The logging level (LOG_LEVEL, default INFO). Set it to DEBUG to see the routine background-loop lines."""
    level = os.getenv('LOG_LEVEL', 'INFO').strip().upper()
    return level if level in ('DEBUG', 'INFO', 'WARNING', 'ERROR') else 'INFO'


def guild_id() -> int | None:
    """The server the bot runs in (DISCORD_GUILD), or None to sync commands globally."""
    value = os.getenv('DISCORD_GUILD')
    return int(value) if value else None


def admin_user_id() -> int:
    """The user ID of the server admin the bot pings and DMs (HALLYU_ID)."""
    value = os.getenv('HALLYU_ID')
    return int(value) if value else DEFAULT_ADMIN_USER_ID


def heartbeat_path() -> Path:
    """The file the bot touches every minute while connected, which the container healthcheck reads (HEARTBEAT_PATH)."""
    return Path(os.getenv('HEARTBEAT_PATH') or Path(tempfile.gettempdir()) / 'iu-bot-heartbeat')


def youtube_token_path() -> str | None:
    """Where the YouTube OAuth token.json lives (TOKEN_DIR)."""
    return os.getenv('TOKEN_DIR')
