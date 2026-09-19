"""Helpers shared by the background tasks."""

import functools
import logging

logger = logging.getLogger('iu-bot')


def keep_running(task_body):
    """
    Wraps the body of a tasks.loop so an unexpected error is logged and the next tick still runs.

    Without this, an unhandled exception stops a tasks.loop for good and the feature silently stops
    working until the bot is restarted. Apply it directly under @tasks.loop(...).
    """
    @functools.wraps(task_body)
    async def wrapper(*args, **kwargs):
        try:
            return await task_body(*args, **kwargs)
        except Exception:
            logger.exception("Unhandled error in %s; it will run again on the next tick.", task_body.__name__)
            return None

    return wrapper
