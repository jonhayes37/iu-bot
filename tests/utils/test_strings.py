"""Tests for utils/strings.py"""

import pytest

from db.listen_game import Standing
from utils.strings import generate_leaderboard_text, get_ordinal


@pytest.mark.parametrize("number, expected", [
    (1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (9, "9th"), (10, "10th"),
    # 11-13 are the exceptions to the st/nd/rd rule, in every hundred
    (11, "11th"), (12, "12th"), (13, "13th"),
    (21, "21st"), (22, "22nd"), (23, "23rd"), (24, "24th"),
    (100, "100th"), (101, "101st"), (111, "111th"), (112, "112th"), (113, "113th"), (121, "121st"),
    (0, "0th"),
])
def test_get_ordinal(number, expected):
    assert get_ordinal(number) == expected


def test_leaderboard_has_header_and_a_line_per_player():
    text = generate_leaderboard_text([Standing(user_id=10, score=30), Standing(user_id=20, score=12)])

    assert text.startswith("🏆 **Listen Game - Final Leaderboard** 🏆\n")
    assert "Thank you all for playing! Here are the final standings:" in text
    assert "🥇 **1st:** <@10> — 30 pts\n" in text
    assert "🥈 **2nd:** <@20> — 12 pts\n" in text


def test_leaderboard_medals_stop_after_third_place():
    board = [Standing(user_id=i, score=100 - i) for i in range(1, 6)]

    lines = generate_leaderboard_text(board).splitlines()[3:]

    assert [line[:1] for line in lines[:3]] == ["🥇", "🥈", "🥉"]
    # Fourth place onwards have no medal: the line starts with a space, then the bold ordinal
    assert lines[3] == " **4th:** <@4> — 96 pts"
    assert lines[4] == " **5th:** <@5> — 95 pts"


def test_leaderboard_keeps_the_order_it_is_given():
    text = generate_leaderboard_text([Standing(user_id=2, score=1), Standing(user_id=1, score=99)])

    assert text.index("<@2>") < text.index("<@1>")


def test_empty_leaderboard_is_just_the_header():
    text = generate_leaderboard_text([])

    assert text.endswith("Here are the final standings:\n\n")
    assert "<@" not in text
