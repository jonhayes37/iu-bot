"""Tests for triggers/message.py: the keyword replies and the ping reply."""

import random

import pytest

from config import MEDIA_DIR
from triggers.message import (
    TRIGGER_LIST, check_chance, check_message_for_replies, find_unique_triggers, is_subword, pick_trigger,
    reply_with_gif, respond_to_ping, send_messages
)


class TestTriggerList:
    """The list of keywords and what they answer with must be self-consistent."""

    def test_every_reply_has_its_picture_in_the_media_folder(self):
        for keyword, options in TRIGGER_LIST.items():
            for option in options:
                filename = option.get("filename")
                if filename:
                    folder = "gifs" if filename.endswith(".gif") else "images"
                    assert (MEDIA_DIR / folder / filename).is_file(), f"{keyword}: {filename} is missing"

    def test_every_reply_says_or_shows_something(self):
        for keyword, options in TRIGGER_LIST.items():
            assert options and all(o.get("content") or o.get("filename") for o in options), keyword

    def test_weights_and_chances_are_sensible(self):
        for keyword, options in TRIGGER_LIST.items():
            assert all(o.get("weight", 1) > 0 for o in options), keyword
            assert all(0 < o.get("chance", 1) <= 1 for o in options), keyword

    def test_keywords_are_lowercase_because_messages_are_lowercased_before_matching(self):
        assert all(keyword == keyword.lower() for keyword in TRIGGER_LIST)


class TestIsSubword:
    """A keyword inside a longer word doesn't count; next to punctuation or spaces it does."""

    @pytest.mark.parametrize("text, subword", [
        ("iu", False),                    # the whole message
        ("hello iu!", False),             # punctuation after it
        ("iu's new song", False),
        ("i love iu", False),
        ("(iu)", False),
        ("medium", True),                 # inside a word
        ("premium", True),
        ("iuna", True),                   # starts a longer word
        ("ciu", True),                    # ends a longer word
        ("iu and medium", False),         # one real use is enough...
        ("medium and iu", False),
        ("medium and premium", True),     # ...but two hidden ones are not
        ("2iu", True),                    # digits count as letters
    ])
    def test_iu(self, text, subword):
        assert is_subword(text, "iu") is subword

    def test_words_in_hangul_and_multi_word_keywords(self):
        assert is_subword("엄정화 좋아", "엄정화") is False
        assert is_subword("best song ever", "best song") is False


class TestPickTrigger:
    """Some keywords have several replies, picked by weight."""

    def test_a_keyword_with_one_reply_always_gives_it(self):
        assert pick_trigger("ditto") == {"filename": "ditto.gif"}

    @pytest.mark.parametrize("roll, expected", [
        (1, "jihyo.gif"), (60, "jihyo.gif"),           # 60% of the range
        (61, "eunbi.gif"), (95, "eunbi.gif"),          # 35%
        (96, "eunbi2.gif"), (100, "eunbi2.gif"),       # 5%
    ])
    def test_replies_are_chosen_by_their_weights(self, monkeypatch, roll, expected):
        monkeypatch.setattr(random, "randint", lambda low, high: roll)

        assert pick_trigger("mother")["filename"] == expected

    def test_the_roll_covers_exactly_the_total_weight(self, monkeypatch):
        seen = []
        monkeypatch.setattr(random, "randint", lambda low, high: seen.append((low, high)) or 1)

        pick_trigger("mother")
        pick_trigger("iu")
        pick_trigger("rollercoaster")             # two options with no weight: 100 each

        assert seen == [(1, 100), (1, 100), (1, 200)]

    def test_replies_without_a_weight_are_equally_likely(self, monkeypatch):
        monkeypatch.setattr(random, "randint", lambda low, high: 101)

        assert pick_trigger("rollercoaster")["filename"] == "nmixx_rollercoaster.gif"


class TestCheckChance:
    """Some replies only happen some of the time."""

    def test_a_reply_without_a_chance_always_happens(self):
        assert check_chance({"filename": "x.gif"}) is True

    @pytest.mark.parametrize("roll, happens", [(0.0, True), (0.19, True), (0.2, False), (0.99, False)])
    def test_a_reply_with_a_chance_happens_when_the_roll_is_below_it(self, monkeypatch, roll, happens):
        monkeypatch.setattr(random, "random", lambda: roll)

        assert check_chance({"filename": "x.gif", "chance": 0.2}) is happens


class TestFindUniqueTriggers:
    """Which keywords a message contains."""

    @pytest.mark.parametrize("text, expected", [
        ("me at 2am", {"2am"}),
        ("what is the best song ever", {"best song"}),
        ("i love iu", {"iu"}),
        ("엄정화 is great", {"엄정화"}),
        ("nothing here", set()),
        ("", set()),
    ])
    def test_simple_messages(self, text, expected):
        assert find_unique_triggers(text) == expected

    @pytest.mark.parametrize("text", ["clownfish", "medium", "rumours", "the sunnyside", "coined"])
    def test_a_keyword_inside_a_longer_word_is_ignored(self, text):
        assert find_unique_triggers(text) == set()

    def test_several_keywords_in_one_message_all_reply(self):
        assert find_unique_triggers("2am and tipsy but also ditto") >= {"2am", "ditto"}

    def test_keywords_that_would_send_the_same_picture_reply_only_once(self):
        found = find_unique_triggers("i want ramen and noodles")

        assert len(found & {"ramen", "noodles"}) == 1

    def test_the_two_spellings_of_a_phrase_reply_once(self):
        assert len(find_unique_triggers("blackpink in your area in my area") & {"in my area", "in your area"}) == 1

    def test_a_keyword_in_a_link_still_counts(self):
        # Words in link slugs are meant to trigger
        assert find_unique_triggers("watch https://youtu.be/sunny now") == {"sunny"}

    @pytest.mark.parametrize("text", ["6 7", "six or seven", "6, maybe 7", "6 or 7 lol"])
    def test_the_six_seven_joke_triggers_in_plain_text(self, text):
        assert any(TRIGGER_LIST[t][0].get("skip_url") for t in find_unique_triggers(text))

    @pytest.mark.parametrize("text", ["https://example.com/6-7", "https://example.com/a?x=6 7", "see https://x.com/6"])
    def test_the_six_seven_joke_ignores_numbers_that_are_only_inside_a_link(self, text):
        assert not any(TRIGGER_LIST[t][0].get("skip_url") for t in find_unique_triggers(text))

    def test_the_six_seven_joke_still_triggers_beside_a_link(self):
        assert find_unique_triggers("6 7 https://youtu.be/dQw4w9WgXcQ") == {"6 7"}

    def test_purple_kiss_does_not_also_trigger_purple(self):
        assert find_unique_triggers("i love purple kiss") == {"purple kiss"}

    def test_purple_alone_triggers_purple(self):
        assert find_unique_triggers("purple") == {"purple"}

    @pytest.mark.parametrize("text", ["girls generation", "girls' generation", "girls-generation", "girls'-generation"])
    def test_girls_generation_does_not_trigger_the_generation_reply(self, text):
        assert find_unique_triggers(text) == set()

    def test_generation_alone_does_trigger(self):
        assert find_unique_triggers("new generation") == {"generation"}

    def test_ballad_only_replies_when_the_message_has_a_link(self):
        assert find_unique_triggers("i like ballads") == set()
        assert find_unique_triggers("ballad") == set()
        assert find_unique_triggers("ballad https://youtu.be/dQw4w9WgXcQ") == {"ballad"}
        assert find_unique_triggers("ballads https://youtu.be/dQw4w9WgXcQ") == {"ballads"}

    @pytest.mark.parametrize("word", ["preacher", "preach", "father"])
    def test_the_preacher_reply_on_a_normal_day(self, frozen_time, word):
        frozen_time("2026-03-13 18:00:00")               # a Friday

        assert find_unique_triggers(f"praise {word}") == {word}

    @pytest.mark.parametrize("word", ["preacher", "preach", "father"])
    def test_on_saturday_the_special_saturday_reply_replaces_it(self, frozen_time, word):
        frozen_time("2026-03-14 18:00:00")               # a Saturday afternoon in New York

        assert find_unique_triggers(f"praise {word}") == {"preacher_is_saturday_currently"}

    def test_saturday_is_decided_by_new_york_time(self, frozen_time):
        frozen_time("2026-03-14 03:00:00")               # still Friday night in New York

        assert find_unique_triggers("praise preacher") == {"preacher"}

    def test_the_saturday_reply_is_not_used_when_no_preacher_word_is_present(self, frozen_time):
        frozen_time("2026-03-14 18:00:00")

        assert find_unique_triggers("hello") == set()


class TestReplyWithGif:
    """Sending a reply with its picture."""

    async def test_a_gif_comes_from_the_gifs_folder(self, make_message):
        message = make_message("x")

        await reply_with_gif(message, "Me most nights at 2am", "drunk.gif")

        message.reply.assert_awaited_once()
        assert message.reply.await_args.args == ("Me most nights at 2am",)
        assert message.reply.await_args.kwargs["file"].filename == "drunk.gif"

    async def test_a_still_picture_comes_from_the_images_folder(self, make_message):
        message = make_message("x")

        await reply_with_gif(message, "", "key_clown.jpg")

        assert message.reply.await_args.kwargs["file"].filename == "key_clown.jpg"

    async def test_text_only_replies_send_no_file(self, make_message):
        message = make_message("x")

        await reply_with_gif(message, "엄정화 detected", None)

        message.reply.assert_awaited_once_with("엄정화 detected")


class TestSendMessages:
    """Each keyword found gets its reply, subject to its chance."""

    async def test_replies_once_for_each_keyword(self, make_message):
        message = make_message("x")

        await send_messages(message, ["ditto", "2am"])

        assert message.reply.await_count == 2

    async def test_a_keyword_with_no_text_replies_with_an_empty_string_and_its_picture(self, make_message):
        message = make_message("x")

        await send_messages(message, ["ditto"])

        assert message.reply.await_args.args == ("",)

    async def test_a_reply_that_fails_its_chance_is_skipped(self, make_message, monkeypatch):
        monkeypatch.setattr(random, "random", lambda: 0.99)
        message = make_message("x")

        await send_messages(message, ["heart"])          # 50% chance

        message.reply.assert_not_awaited()

    async def test_a_reply_that_passes_its_chance_is_sent(self, make_message, monkeypatch):
        monkeypatch.setattr(random, "random", lambda: 0.01)
        message = make_message("x")

        await send_messages(message, ["heart"])

        assert message.reply.await_args.kwargs["file"].filename == "chuu_heart.gif"


class TestCheckMessageForReplies:
    """The entry point for every message."""

    async def test_matching_ignores_case(self, make_message):
        message = make_message("ME AT 2AM")

        await check_message_for_replies(message)

        assert message.reply.await_args.kwargs["file"].filename == "drunk.gif"

    async def test_a_message_with_no_keywords_gets_no_reply(self, make_message):
        message = make_message("just chatting about the weather")

        await check_message_for_replies(message)

        message.reply.assert_not_awaited()

    async def test_a_message_with_several_keywords_gets_several_replies(self, make_message):
        message = make_message("2am and ditto")

        await check_message_for_replies(message)

        assert message.reply.await_count == 2


class TestRespondToPing:
    """Mentioning the bot gets a reply, except an @everyone."""

    async def test_replies_to_a_mention(self, make_message):
        message = make_message("<@1> hello")
        message.mention_everyone = False

        await respond_to_ping(message)

        assert message.reply.await_args.args == ("IU at your service!",)
        assert message.reply.await_args.kwargs["file"].filename == "ping.gif"

    async def test_an_at_everyone_does_not_count_as_a_ping(self, make_message):
        message = make_message("@everyone hello")
        message.mention_everyone = True

        await respond_to_ping(message)

        message.reply.assert_not_awaited()
