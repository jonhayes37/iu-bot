"""Helpers for building Discord attachments."""

import io

import discord


def text_file(text: str, filename: str) -> discord.File:
    """Wraps text in an in-memory UTF-8 text attachment."""
    return discord.File(io.BytesIO(text.encode('utf-8')), filename=filename)
