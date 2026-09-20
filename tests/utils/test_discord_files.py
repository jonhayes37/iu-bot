"""Tests for utils/discord_files.py"""

import discord

from utils.discord_files import text_file


def test_wraps_text_in_a_named_attachment():
    attachment = text_file("hello", "notes.txt")

    assert isinstance(attachment, discord.File)
    assert attachment.filename == "notes.txt"
    assert attachment.fp.read() == b"hello"


def test_encodes_as_utf8():
    attachment = text_file("아이유 🎵", "songs.txt")

    assert attachment.fp.read().decode("utf-8") == "아이유 🎵"


def test_empty_text_is_an_empty_attachment():
    assert text_file("", "empty.txt").fp.read() == b""


def test_long_text_is_not_truncated():
    text = "x" * 50_000

    assert len(text_file(text, "long.txt").fp.read()) == 50_000
