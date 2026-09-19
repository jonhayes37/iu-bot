"""Errors raised by the db/ modules that aren't sqlite3 errors."""


class InvalidStateError(Exception):
    """
    A change was refused because the thing it applies to has moved on: for example, skipping a round
    whose results are already being revealed. Nothing was changed. This normally means two people
    acted at nearly the same time, or someone used an out-of-date button.
    """
