"""Tests for commands/hearts.py: checking a balance and the admin heart tools."""

import logging
import random

import discord
import pytest

from commands.hearts import check_balance, modify_balance, random_award
from config import Channel, Database
from db.merch import get_user_balance, modify_db_balance


@pytest.fixture(autouse=True)
def _merch_database(databases):
    databases(Database.MERCH)


class TestCheckBalance:
    """/check-balance, only in #merch-booth."""

    async def test_only_works_in_the_merch_booth(self, make_interaction):
        interaction = make_interaction(channel="general")

        await check_balance.callback(interaction)

        assert interaction.sent[0].content == "This command can only be used in the #merch-booth channel."
        assert interaction.sent[0].ephemeral

    async def test_shows_the_balance_publicly(self, make_interaction):
        interaction = make_interaction(channel=Channel.MERCH_BOOTH)
        modify_db_balance(1, interaction.user.id, 25, "gift")

        await check_balance.callback(interaction)

        [reply] = interaction.sent
        assert not reply.ephemeral
        assert reply.embed.title == "🎫 Your Wallet"
        assert reply.embed.description == "You currently have **25 hearts** available to spend."
        assert reply.embed.footer.text == "Use /view-merch to see what you can buy!"

    @pytest.mark.parametrize("hearts, text", [(0, "0 hearts"), (1, "1 heart"), (2, "2 hearts")])
    async def test_hearts_is_singular_only_for_one(self, make_interaction, hearts, text):
        interaction = make_interaction(channel=Channel.MERCH_BOOTH)
        if hearts:
            modify_db_balance(1, interaction.user.id, hearts, "gift")

        await check_balance.callback(interaction)

        assert f"**{text}**" in interaction.sent[0].embed.description


class TestModifyBalance:
    """/modify-balance, in #dispatch-news."""

    async def test_only_works_in_dispatch_news_and_changes_nothing_elsewhere(self, make_interaction, make_member,
                                                                              caplog):
        interaction = make_interaction(channel="general", administrator=True)
        target = make_member(user_id=50)

        with caplog.at_level(logging.ERROR, logger="iu-bot"):
            await modify_balance.callback(interaction, target, 10, "test")

        assert interaction.sent[0].content == "This command can only be used in the #dispatch-news channel."
        assert get_user_balance(50) == 0
        assert "Wrong channel for balance modification" in caplog.text

    async def test_awarding_hearts(self, make_interaction, make_member, query):
        interaction = make_interaction(channel=Channel.DISPATCH_NEWS, administrator=True)
        target = make_member(user_id=50)

        await modify_balance.callback(interaction, target, 10, "Contest winner")

        assert get_user_balance(50) == 10
        [reply] = interaction.sent
        assert not reply.ephemeral
        embed = reply.embed
        assert embed.title == "Balance Modification" and embed.color == discord.Color.green()
        assert [(f.name, f.value) for f in embed.fields] == [
            ("User", target.mention), ("Amount", "Awarded 10 hearts"), ("Reason", "Contest winner")]
        assert embed.footer.text == f"Authorized by {interaction.user.display_name}"
        tx = query(Database.MERCH, "SELECT * FROM transactions")[0]
        assert (tx["sender_id"], tx["receiver_id"], tx["amount"], tx["reason"]) == \
            (f"ADMIN:{interaction.user.id}", 50, 10, "Contest winner")

    async def test_deducting_hearts(self, make_interaction, make_member):
        interaction = make_interaction(channel=Channel.DISPATCH_NEWS, administrator=True)
        target = make_member(user_id=50)
        modify_db_balance(1, 50, 10, "start")

        await modify_balance.callback(interaction, target, -4, "Correction")

        assert get_user_balance(50) == 6
        embed = interaction.sent[0].embed
        assert embed.color == discord.Color.red()
        assert embed.fields[1].value == "Deducted 4 hearts"

    @pytest.mark.parametrize("amount, text", [
        (1, "Awarded 1 heart"), (-1, "Deducted 1 heart"), (0, "Awarded 0 hearts")])
    async def test_hearts_is_singular_only_for_one(self, make_interaction, make_member, amount, text):
        interaction = make_interaction(channel=Channel.DISPATCH_NEWS, administrator=True)

        await modify_balance.callback(interaction, make_member(user_id=50), amount, "x")

        assert interaction.sent[0].embed.fields[1].value == text


class TestRandomAward:
    """/random-award picks one mentioned member at random."""

    @pytest.fixture(name="offered")
    def _predictable_choice(self, monkeypatch):
        """random.choice picks the last candidate; the fixture is the list of candidates it was offered."""
        offered = []

        def choose_last(candidates):
            offered.append(list(candidates))
            return candidates[-1]

        monkeypatch.setattr(random, "choice", choose_last)
        return offered

    async def test_only_works_in_dispatch_news(self, make_interaction):
        interaction = make_interaction(channel="general", administrator=True)

        await random_award.callback(interaction, "<@1>", 5, "x")

        assert interaction.sent[0].content == "This command can only be used in the #dispatch-news channel."

    @pytest.mark.parametrize("text", ["", "nobody", "@Alice @Bob", "<@abc>", "<#123>"])
    async def test_without_real_mentions_it_asks_for_them(self, make_interaction, text):
        interaction = make_interaction(channel=Channel.DISPATCH_NEWS, administrator=True)

        await random_award.callback(interaction, text, 5, "x")

        [reply] = interaction.sent
        assert reply.content.startswith("I couldn't find any valid user mentions.")
        assert reply.ephemeral

    async def test_the_winner_is_paid_and_announced(self, make_interaction, query, offered):
        interaction = make_interaction(channel=Channel.DISPATCH_NEWS, administrator=True)

        await random_award.callback(interaction, "<@11> <@22> <@33>", 7, "Watch Party Attendee")

        winner = int(offered[0][-1])
        assert get_user_balance(winner) == 7
        assert query(Database.MERCH, "SELECT reason FROM transactions")[0]["reason"] == \
            "Random Award: Watch Party Attendee"
        [reply] = interaction.sent
        assert not reply.ephemeral
        embed = reply.embed
        assert embed.title == "Random Award Winner!"
        assert [(f.name, f.value) for f in embed.fields] == [
            ("Winner", f"<@{winner}>"), ("Prize", "**7 hearts!**"), ("Reason", "Watch Party Attendee")]
        assert embed.footer.text == f"Rolled by {interaction.user.display_name}"

    async def test_everyone_mentioned_is_a_candidate_once(self, make_interaction, offered):
        interaction = make_interaction(channel=Channel.DISPATCH_NEWS, administrator=True)

        await random_award.callback(interaction, "<@11> <@11> <@22> <@!33> <@33>", 1, "x")

        assert sorted(offered[0]) == ["11", "22", "33"]      # repeating a mention doesn't improve the odds

    @pytest.mark.usefixtures("offered")
    async def test_nickname_style_mentions_count(self, make_interaction):
        interaction = make_interaction(channel=Channel.DISPATCH_NEWS, administrator=True)

        await random_award.callback(interaction, "<@!44>", 1, "x")

        assert get_user_balance(44) == 1

    async def test_the_odds_are_even_between_candidates(self, make_interaction):
        wins = {"11": 0, "22": 0}
        random.seed(99)
        for _ in range(200):
            interaction = make_interaction(channel=Channel.DISPATCH_NEWS, administrator=True)
            await random_award.callback(interaction, "<@11> <@22>", 1, "x")
            wins[interaction.sent[0].embed.fields[0].value[2:-1]] += 1

        assert 70 < wins["11"] < 130
