"""IU Bot for the HallyU Discord server"""

import logging
import signal

from bot import IUBot
from config import discord_token
from db.initialize import initialize_databases


def main():
    """Sets up the databases and runs the bot until it is stopped."""
    logging.basicConfig(level=logging.INFO)

    # Graceful shutdown from docker stop
    signal.signal(signal.SIGTERM, lambda *_: signal.raise_signal(signal.SIGINT))

    # Run database setup before starting the bot
    initialize_databases()
    IUBot().run(discord_token())


if __name__ == "__main__":
    main()
