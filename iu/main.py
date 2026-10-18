"""IU Bot for the HallyU Discord server"""

import logging
import signal
import socket
import time

from bot import IUBot
from config import discord_token, log_level
from db.initialize import initialize_databases

logger = logging.getLogger(__name__)

DISCORD_HOST = "discord.com"
FIRST_RETRY_SECONDS = 5
MAX_RETRY_SECONDS = 60


def wait_for_network():
    """Blocks until Discord's address can be looked up.

    After a power cut the NAS can start the container before the router has internet, and discord.py
    gives up on its first login instead of retrying, so the bot waits here rather than exiting.
    """
    delay = FIRST_RETRY_SECONDS
    waited = False
    while True:
        try:
            socket.getaddrinfo(DISCORD_HOST, 443)
        except socket.gaierror as ex:
            logger.warning("Can't look up %s yet (%s); trying again in %d seconds", DISCORD_HOST, ex, delay)
            time.sleep(delay)
            delay = min(delay * 2, MAX_RETRY_SECONDS)
            waited = True
            continue
        if waited:
            logger.info("The network is up; connecting to Discord.")
        return


def main():
    """Sets up the databases and runs the bot until it is stopped."""
    logging.basicConfig(level=log_level())

    # Graceful shutdown from docker stop
    signal.signal(signal.SIGTERM, lambda *_: signal.raise_signal(signal.SIGINT))

    # Run database setup before starting the bot
    initialize_databases()
    try:
        wait_for_network()
    except KeyboardInterrupt:
        return      # docker stop while waiting for the network
    IUBot().run(discord_token())


if __name__ == "__main__":
    main()
