"""Tests for services/listen_game_reveal.py

A reveal posts several messages with pauses between them, saving its progress (`reveal_step`) after each
so a restart carries on where it stopped. The pauses are skipped here.
"""

import asyncio
import logging

import pytest

from config import Database, Role
from db.listen_game import (
    GameStatus, RoundStatus, Standing, Submission, get_current_round_db, get_game_by_status_db, get_round_db,
    set_reveal_step_db, skip_game_turn_db, update_round_playlist_db
)
from services import listen_game_reveal as reveal
from services.listen_game_reveal import (
    REVEAL_DELAY_SECONDS, _active_reveals, _build_round_summary, _post_game_over, _reveal, _reveal_tasks, _run_reveal,
    start_reveal
)
from testsupport.listen_game import reveal_ready_round, start_game


@pytest.fixture(autouse=True)
def _listen_game_database(databases):
    databases(Database.LISTEN_GAME)


@pytest.fixture(autouse=True, name="pauses")
def _pauses(monkeypatch):
    """Skips the waits between messages, recording how long each would have been."""
    waited = []

    async def no_wait(seconds):
        waited.append(seconds)

    monkeypatch.setattr(reveal.asyncio, "sleep", no_wait)
    return waited


@pytest.fixture(name="channel")
def _channel(make_channel, make_guild):
    """The #listen-game channel, in a server that has the Listen Game Player role."""
    game_channel = make_channel("listen-game")
    game_channel.guild = make_guild(roles=(Role.LISTEN_GAME_PLAYER,))
    return game_channel


def _texts(channel):
    return [message.content for message in channel.sent]


def _role_mention(channel):
    return channel.guild.roles[0].mention


def _mid_game():
    """Players 101, 102, 103: 101 has listened; 103 came 2nd and 102 came 1st. 102 hosts next."""
    game_id = start_game()
    round_id = reveal_ready_round(game_id, [(102, "Song by 102"), (103, "Song by 103")])
    return game_id, round_id


def _final_turn():
    """Two players. 101's turn was skipped, so 102 is the last listener, and 101's song came first."""
    game_id = start_game((101, 102))
    skip_game_turn_db(game_id, get_current_round_db(game_id).round_id)
    round_id = reveal_ready_round(game_id, [(101, "Song by 101")])
    return game_id, round_id


class TestRevealMidGame:
    """A reveal for a round that is not the last turn."""

    async def test_posts_the_intro_then_each_song_worst_first_then_the_summary(self, channel):
        _, round_id = _mid_game()

        await _reveal(channel, round_id)

        texts = _texts(channel)
        assert len(texts) == 4
        assert texts[0] == f"🎧 **{_role_mention(channel)}, <@101> has finished their rankings! Here are the results:**"
        assert texts[1] == "**2nd: [Song by 103](<https://youtu.be/vid103>)**\nComment 2"
        assert texts[2] == "**1st: [Song by 102](<https://youtu.be/vid102>)**\nComment 1"
        assert texts[3].startswith("🎉 **Round complete!**")

    async def test_the_summary_lists_results_standings_and_who_is_next(self, channel):
        _, round_id = _mid_game()

        await _reveal(channel, round_id)

        summary = _texts(channel)[-1]
        assert "1st: <@102> - **Song by 102** (9 pts)" in summary
        assert "2nd: <@103> - **Song by 103** (8 pts)" in summary
        assert "1st - <@102> (9 pts)\n2nd - <@103> (8 pts)\n3rd - <@101> (0 pts)" in summary
        assert summary.endswith(
            "The next listener is <@102>! Use `/listen-game-post-ruleset` when you are ready to begin.")

    async def test_the_round_is_completed_and_the_next_one_opened(self, channel):
        game_id, round_id = _mid_game()

        await _reveal(channel, round_id)

        assert get_round_db(round_id).status is RoundStatus.COMPLETED
        next_round = get_current_round_db(game_id)
        assert (next_round.host_id, next_round.status) == (102, RoundStatus.SETTING_THEME)
        assert get_game_by_status_db(GameStatus.PLAYING).game_id == game_id

    async def test_progress_is_saved_after_every_message(self, channel):
        _, round_id = _mid_game()

        await _reveal(channel, round_id)

        # intro=1, two songs=2 and 3, summary=len(songs)+2=4
        assert get_round_db(round_id).reveal_step == 4

    async def test_a_pause_follows_the_intro_and_each_song(self, channel, pauses):
        _, round_id = _mid_game()

        await _reveal(channel, round_id)

        assert pauses == [REVEAL_DELAY_SECONDS] * 3

    async def test_without_the_player_role_the_intro_just_names_the_listener(self, make_channel, make_guild):
        bare = make_channel("listen-game")
        bare.guild = make_guild(roles=())
        _, round_id = _mid_game()

        await _reveal(bare, round_id)

        assert _texts(bare)[0] == "🎧 **<@101> has finished their rankings! Here are the results:**"


class TestResumingAReveal:
    """After a restart the reveal carries on without repeating anything."""

    async def test_resumes_after_the_intro_and_first_song(self, channel):
        _, round_id = _mid_game()
        set_reveal_step_db(round_id, 2)          # intro and the 2nd place song are already posted

        await _reveal(channel, round_id)

        texts = _texts(channel)
        assert len(texts) == 2
        assert texts[0].startswith("**1st: [Song by 102]")
        assert texts[1].startswith("🎉 **Round complete!**")

    async def test_resumes_after_only_the_intro(self, channel):
        _, round_id = _mid_game()
        set_reveal_step_db(round_id, 1)

        await _reveal(channel, round_id)

        assert len(_texts(channel)) == 3
        assert not _texts(channel)[0].startswith("🎧")

    async def test_resumes_after_every_song_but_before_the_summary(self, channel):
        _, round_id = _mid_game()
        set_reveal_step_db(round_id, 3)

        await _reveal(channel, round_id)

        assert len(_texts(channel)) == 1
        assert _texts(channel)[0].startswith("🎉 **Round complete!**")

    async def test_resumes_after_the_summary_by_only_moving_the_game_on(self, channel):
        game_id, round_id = _mid_game()
        set_reveal_step_db(round_id, 4)

        await _reveal(channel, round_id)

        assert _texts(channel) == []
        assert get_round_db(round_id).status is RoundStatus.COMPLETED
        assert get_current_round_db(game_id).host_id == 102

    async def test_a_reveal_that_already_finished_does_nothing(self, channel):
        _, round_id = _mid_game()
        await _reveal(channel, round_id)
        channel.sent.clear()

        await _reveal(channel, round_id)

        assert _texts(channel) == []

    @pytest.mark.parametrize("prepare", ["unknown", "not_revealing"])
    async def test_a_round_that_is_not_waiting_for_a_reveal_is_left_alone(self, channel, prepare, caplog):
        if prepare == "unknown":
            round_id = 999
        else:
            round_id = get_current_round_db(start_game()).round_id

        with caplog.at_level(logging.INFO, logger="iu-bot"):
            await _reveal(channel, round_id)

        assert _texts(channel) == []
        assert "is not waiting on a reveal" in caplog.text


class TestRevealOfTheLastTurn:
    """The last reveal also ends the game."""

    async def test_posts_the_summary_without_a_next_listener_then_the_game_over_messages(self, channel):
        _, round_id = _final_turn()

        await _reveal(channel, round_id)

        texts = _texts(channel)
        assert len(texts) == 5
        assert texts[3].startswith("🏆 **Listen Game - Final Leaderboard** 🏆")
        assert "**1st:** <@101> — 9 pts" in texts[3]
        assert "The next listener" not in texts[2]
        assert texts[4].startswith("🎶 **Here's all of the playlists from this game:**")

    async def test_the_game_is_finished(self, channel):
        game_id, round_id = _final_turn()

        await _reveal(channel, round_id)

        assert get_game_by_status_db(GameStatus.FINISHED).game_id == game_id
        assert get_round_db(round_id).status is RoundStatus.COMPLETED
        assert get_current_round_db(game_id) is None

    async def test_progress_includes_the_game_over_step(self, channel):
        _, round_id = _final_turn()

        await _reveal(channel, round_id)

        # intro=1, one song=2, summary=3, game over=4
        assert get_round_db(round_id).reveal_step == 4

    async def test_every_rounds_playlist_is_listed(self, channel):
        _, round_id = _final_turn()
        first_round, last_round = get_round_db(round_id - 1), get_round_db(round_id)
        update_round_playlist_db(last_round.round_id, "PLlast")

        await _reveal(channel, round_id)

        playlists = _texts(channel)[-1].splitlines()
        assert playlists[1] == f"**Round 1** (<@{first_round.host_id}>): *No playlist generated*"
        assert playlists[2] == f"**Round 2** (<@{last_round.host_id}>): https://www.youtube.com/playlist?list=PLlast"

    async def test_resuming_after_the_summary_still_posts_the_game_over_messages(self, channel):
        _, round_id = _final_turn()
        set_reveal_step_db(round_id, 3)

        await _reveal(channel, round_id)

        texts = _texts(channel)
        assert len(texts) == 2
        assert texts[0].startswith("🏆")

    async def test_resuming_after_the_game_over_messages_does_not_repeat_them(self, channel):
        game_id, round_id = _final_turn()
        set_reveal_step_db(round_id, 4)

        await _reveal(channel, round_id)

        assert _texts(channel) == []
        assert get_game_by_status_db(GameStatus.FINISHED).game_id == game_id

    async def test_a_short_pause_lets_the_leaderboard_land_first(self, channel, pauses):
        _, round_id = _final_turn()

        await _reveal(channel, round_id)

        assert pauses[-1] == 2


async def test_a_game_that_cannot_be_advanced_is_an_error(channel, monkeypatch):
    _, round_id = _mid_game()
    monkeypatch.setattr("services.listen_game_reveal.advance_game_turn_db", lambda *_: False)

    with pytest.raises(RuntimeError, match="Could not advance game"):
        await _reveal(channel, round_id)


async def test_a_game_with_no_rounds_only_gets_the_leaderboard(channel):
    await _post_game_over(channel, 999)

    assert len(_texts(channel)) == 1
    assert _texts(channel)[0].startswith("🏆")


class TestRoundSummary:
    """The message after the songs, built without a database."""

    RESULTS = [Submission(round_id=1, user_id=5, video_id="v", raw_title="Song A", rank=1, points_awarded=9),
               Submission(round_id=1, user_id=6, video_id="w", raw_title="Song B", rank=2, points_awarded=8)]

    def test_lists_results_standings_and_the_next_listener(self):
        summary = _build_round_summary(
            self.RESULTS, [Standing(5, 9), Standing(6, 8)], next_host_id=7)

        assert summary == (
            "🎉 **Round complete!**\n\n"
            "**Last Round's Results**\n1st: <@5> - **Song A** (9 pts)\n2nd: <@6> - **Song B** (8 pts)\n\n"
            "**Current Ranking**\n1st - <@5> (9 pts)\n2nd - <@6> (8 pts)\n\n"
            "The next listener is <@7>! Use `/listen-game-post-ruleset` when you are ready to begin.")

    def test_no_next_listener_after_the_last_turn(self):
        summary = _build_round_summary(self.RESULTS, [Standing(5, 9)], next_host_id=None)

        assert summary.endswith("**Current Ranking**\n1st - <@5> (9 pts)\n\n")

    def test_an_empty_leaderboard_is_flagged(self):
        summary = _build_round_summary(self.RESULTS, [], next_host_id=None)

        assert "*Error fetching leaderboard.*" in summary


class TestStartReveal:
    """start_reveal runs the reveal in the background, one per round."""

    @pytest.fixture(autouse=True)
    def _clean_slate(self):
        _active_reveals.clear()
        yield
        _active_reveals.clear()

    async def test_runs_the_reveal_in_the_background(self, channel):
        game_id, round_id = _mid_game()

        assert start_reveal(channel, round_id) is True
        await asyncio.gather(*_reveal_tasks)

        assert get_round_db(round_id).status is RoundStatus.COMPLETED
        assert len(_texts(channel)) == 4
        assert get_current_round_db(game_id).host_id == 102

    async def test_a_reveal_already_running_for_the_round_is_not_started_twice(self, channel, monkeypatch):
        release = asyncio.Event()

        async def slow_reveal(*_):
            await release.wait()

        monkeypatch.setattr("services.listen_game_reveal._reveal", slow_reveal)

        assert start_reveal(channel, 5) is True
        assert start_reveal(channel, 5) is False
        assert start_reveal(channel, 6) is True      # other rounds are independent

        release.set()
        await asyncio.gather(*_reveal_tasks)

    async def test_the_round_can_be_started_again_once_it_has_finished(self, channel, monkeypatch):
        monkeypatch.setattr("services.listen_game_reveal._reveal", lambda *_: asyncio.sleep(0))
        start_reveal(channel, 5)
        await asyncio.gather(*_reveal_tasks)

        assert start_reveal(channel, 5) is True
        await asyncio.gather(*_reveal_tasks)

    async def test_finished_tasks_are_forgotten(self, channel, monkeypatch):
        monkeypatch.setattr("services.listen_game_reveal._reveal", lambda *_: asyncio.sleep(0))
        start_reveal(channel, 5)
        await asyncio.gather(*_reveal_tasks)
        await asyncio.sleep(0)

        assert not _reveal_tasks

    async def test_a_reveal_that_fails_is_logged_and_can_be_resumed(self, channel, monkeypatch, caplog):
        async def failing(*_):
            raise ConnectionError("Discord went away")

        monkeypatch.setattr("services.listen_game_reveal._reveal", failing)

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await _run_reveal(channel, 5)

        assert "Reveal for round 5 stopped early" in caplog.text
        assert 5 not in _active_reveals
