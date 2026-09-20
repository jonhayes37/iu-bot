"""Tests for commands/merch.py: the Merch Booth and the raffle."""

import logging
import random

import discord
import pytest

from commands.merch import add_merch, draw_raffle, purchase, purchase_history, view_merch
from config import DEFAULT_ADMIN_USER_ID, Channel, Database
from db.merch import get_all_item_owners, get_user_balance, modify_db_balance, upsert_merch_item


@pytest.fixture(autouse=True)
def _merch_database(databases):
    databases(Database.MERCH)


@pytest.fixture(name="booth")
def _booth(make_guild, make_interaction):
    """A member's interaction in #merch-booth, in a server that also has #dispatch-news."""
    guild = make_guild(channels=(Channel.MERCH_BOOTH, Channel.DISPATCH_NEWS))
    return make_interaction(channel=guild.text_channels[0], guild=guild)


@pytest.fixture(name="dispatch")
def _dispatch(make_guild, make_interaction):
    """An admin's interaction in #dispatch-news."""
    guild = make_guild(channels=(Channel.DISPATCH_NEWS,))
    return make_interaction(channel=guild.text_channels[0], guild=guild, administrator=True)


def _fields(embed):
    return {field.name: field.value for field in embed.fields}


class TestAddMerch:
    """/add-merch (admin, in #dispatch-news)."""

    async def test_only_works_in_dispatch_news(self, make_interaction):
        interaction = make_interaction(channel="general", administrator=True)

        await add_merch.callback(interaction, "sticker", "Sticker", "A sticker", 25, None)

        assert interaction.sent[0].content == "This command can only be used in the #dispatch-news channel."

    @pytest.mark.parametrize("price", [0, -5])
    async def test_an_item_cannot_be_free(self, dispatch, query, price):
        await add_merch.callback(dispatch, "sticker", "Sticker", "A sticker", price, None)

        assert (dispatch.sent[0].content, dispatch.sent[0].ephemeral) == ("Price cannot be free!", True)
        assert query(Database.MERCH, "SELECT * FROM merch_items") == []

    async def test_creates_the_item_and_confirms_it(self, dispatch, query):
        await add_merch.callback(dispatch, "sticker", "Sticker", "A sticker", 25, 3)

        row = query(Database.MERCH, "SELECT * FROM merch_items")[0]
        assert (row["item_id"], row["name"], row["price"], row["max_per_user"]) == ("STICKER", "Sticker", 25, 3)
        embed = dispatch.sent[0].embed
        assert embed.title == "🛒 Merch Booth Updated!"
        assert _fields(embed) == {"SKU": "`STICKER`", "Name": "Sticker", "Price": "25 hearts",
                                  "Stock Limit": "3 per user", "Description": "A sticker"}

    @pytest.mark.parametrize("limit", [None, 0, -2])
    async def test_no_positive_limit_means_unlimited(self, dispatch, query, limit):
        await add_merch.callback(dispatch, "sticker", "Sticker", "A sticker", 25, limit)

        assert _fields(dispatch.sent[0].embed)["Stock Limit"] == "Unlimited"
        assert query(Database.MERCH, "SELECT max_per_user FROM merch_items")[0]["max_per_user"] is None

    async def test_using_an_existing_code_updates_the_item(self, dispatch, query):
        await add_merch.callback(dispatch, "sticker", "Sticker", "A sticker", 25, 3)

        await add_merch.callback(dispatch, "STICKER", "Big Sticker", "Bigger", 40, None)

        rows = query(Database.MERCH, "SELECT * FROM merch_items")
        assert [(r["name"], r["price"]) for r in rows] == [("Big Sticker", 40)]


class TestViewMerch:
    """/view-merch (in #merch-booth)."""

    async def test_only_works_in_the_merch_booth(self, make_interaction):
        interaction = make_interaction(channel="general")

        await view_merch.callback(interaction)

        assert interaction.sent[0].content == "This command can only be used in the #merch-booth channel."

    async def test_an_empty_booth_is_explained_privately(self, booth):
        await view_merch.callback(booth)

        [reply] = booth.sent
        assert reply.content == "The merch booth is currently empty! Tell the admins to stock the shelves."
        assert reply.ephemeral

    async def test_lists_items_cheapest_first_with_the_members_balance(self, booth):
        modify_db_balance(1, booth.user.id, 40, "gift")
        upsert_merch_item("BIG", "Big Thing", "Costly", 100, None)
        upsert_merch_item("SMALL", "Small Thing", "Cheap", 10, None)

        await view_merch.callback(booth)

        [reply] = booth.sent
        assert not reply.ephemeral
        embed = reply.embed
        assert embed.title == "🛍️ The Merch Booth"
        assert "You currently have **40 hearts**." in embed.description
        assert [f.name for f in embed.fields] == ["[10 hearts] **Small Thing** (`SMALL`)",
                                                  "[100 hearts] **Big Thing** (`BIG`)"]

    async def test_shows_how_many_a_member_can_still_buy(self, booth, execute):
        upsert_merch_item("BADGE", "Badge", "A badge", 5, 3)
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (?, 'BADGE', 1)", booth.user.id)
        upsert_merch_item("STICKER", "Sticker", "A sticker", 6, None)

        await view_merch.callback(booth)

        fields = {f.name: f.value for f in booth.sent[0].embed.fields}
        assert fields["[5 hearts] **Badge** (`BADGE`)"] == "A badge\n***2** available*"
        assert fields["[6 hearts] **Sticker** (`STICKER`)"] == "A sticker\n*Unlimited stock*"

    async def test_items_a_member_has_hit_the_limit_on_are_sold_out_and_listed_last(self, booth, execute):
        upsert_merch_item("BADGE", "Badge", "A badge", 5, 1)
        upsert_merch_item("STICKER", "Sticker", "A sticker", 20, None)
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (?, 'BADGE', 1)", booth.user.id)

        await view_merch.callback(booth)

        fields = booth.sent[0].embed.fields
        assert [f.name for f in fields] == ["[20 hearts] **Sticker** (`STICKER`)", "~~Badge (`BADGE`)~~ - **SOLD OUT**"]
        assert fields[1].value == "A badge"

    async def test_sold_out_is_per_member(self, booth, execute):
        upsert_merch_item("BADGE", "Badge", "A badge", 5, 1)
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (999, 'BADGE', 1)")

        await view_merch.callback(booth)

        assert "SOLD OUT" not in booth.sent[0].embed.fields[0].name


class TestPurchase:
    """/purchase (in #merch-booth)."""

    async def test_only_works_in_the_merch_booth(self, make_interaction):
        interaction = make_interaction(channel="general")

        await purchase.callback(interaction, "STICKER")

        assert interaction.sent[0].content == "This command can only be used in the #merch-booth channel."

    async def test_a_successful_purchase_is_celebrated_publicly_and_logged_for_the_admin(self, booth):
        upsert_merch_item("STICKER", "Sticker", "A sticker", 25, None)
        modify_db_balance(1, booth.user.id, 100, "gift")

        await purchase.callback(booth, "sticker")

        assert get_user_balance(booth.user.id) == 75
        [reply] = booth.sent
        assert not reply.ephemeral
        assert reply.embed.title == "🎉 Purchase Successful!"
        assert reply.embed.description == "Successfully purchased **Sticker** for 25 hearts!"
        [log] = booth.guild.text_channels[1].sent
        assert log.content == (f"<@{booth.user.id}> Successfully purchased **Sticker** for 25 hearts! "
                               f"<@{DEFAULT_ADMIN_USER_ID}> will help with redemption.")

    async def test_a_purchase_still_works_if_the_dispatch_channel_is_missing(self, make_guild, make_interaction):
        guild = make_guild(channels=(Channel.MERCH_BOOTH,))
        interaction = make_interaction(channel=guild.text_channels[0], guild=guild)
        upsert_merch_item("STICKER", "Sticker", "A sticker", 25, None)
        modify_db_balance(1, interaction.user.id, 100, "gift")

        await purchase.callback(interaction, "STICKER")

        assert interaction.sent[0].embed.title == "🎉 Purchase Successful!"

    @pytest.mark.parametrize("hearts, item, text", [
        (100, "NOPE", "Could not find an item with SKU `NOPE` in the merch booth!"),
        (10, "STICKER", "You don't have enough hearts! You need **25**, but you only have **10**."),
    ])
    async def test_a_failed_purchase_explains_why_privately(self, booth, hearts, item, text):
        upsert_merch_item("STICKER", "Sticker", "A sticker", 25, None)
        modify_db_balance(1, booth.user.id, hearts, "gift")

        await purchase.callback(booth, item)

        [reply] = booth.sent
        assert reply.ephemeral
        assert (reply.embed.title, reply.embed.description) == ("❌ Purchase Failed", text)
        assert booth.guild.text_channels[1].sent == []          # nothing logged for the admin

    async def test_the_per_member_limit_is_enforced(self, booth):
        upsert_merch_item("BADGE", "Badge", "A badge", 5, 1)
        modify_db_balance(1, booth.user.id, 100, "gift")
        await purchase.callback(booth, "BADGE")
        booth.sent.clear()

        await purchase.callback(booth, "BADGE")

        assert "maximum limit (1) for **Badge**" in booth.sent[0].embed.description


class TestPurchaseHistory:
    """/purchase-history (in #merch-booth)."""

    async def test_only_works_in_the_merch_booth(self, make_interaction):
        interaction = make_interaction(channel="general")

        await purchase_history.callback(interaction)

        assert interaction.sent[0].content == "This command can only be used in the #merch-booth channel."

    async def test_nothing_bought_yet(self, booth):
        await purchase_history.callback(booth)

        [reply] = booth.sent
        assert reply.content == "You haven't bought anything yet! Use `/view-merch` to see what's available."
        assert reply.ephemeral

    async def test_lists_what_was_bought(self, booth):
        upsert_merch_item("BADGE", "Badge", "A badge", 5, None)
        upsert_merch_item("STICKER", "Sticker", "A sticker", 6, None)
        modify_db_balance(1, booth.user.id, 100, "gift")
        await purchase.callback(booth, "BADGE")
        await purchase.callback(booth, "BADGE")
        await purchase.callback(booth, "STICKER")
        booth.sent.clear()

        await purchase_history.callback(booth)

        [reply] = booth.sent
        assert not reply.ephemeral
        assert reply.embed.title == "Your Purchase History"
        assert [(f.name, f.value) for f in reply.embed.fields] == [
            ("Badge (`BADGE`)", "A badge\n*Owned: **2***"), ("Sticker (`STICKER`)", "A sticker\n*Owned: **1***")]


class TestDrawRaffle:
    """/draw-raffle (admin, in #dispatch-news)."""

    async def test_only_works_in_dispatch_news(self, make_interaction):
        interaction = make_interaction(channel="general", administrator=True)

        await draw_raffle.callback(interaction)

        assert interaction.sent[0].content == "This command can only be used in the #dispatch-news channel."

    async def test_with_no_tickets_nobody_wins(self, dispatch):
        await draw_raffle.callback(dispatch)

        [reply] = dispatch.sent
        assert (reply.content, reply.ephemeral) == ("Nobody has bought any raffle tickets yet!", True)

    async def test_the_winner_is_drawn_by_tickets_announced_and_the_pool_reset(self, dispatch, execute, monkeypatch):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (11, 'RAFFLE', 3), (22, 'RAFFLE', 1)")
        seen = {}

        def pick_last(users, weights, k):
            seen.update(zip(users, weights))
            assert k == 1
            return [users[-1]]

        monkeypatch.setattr(random, "choices", pick_last)

        await draw_raffle.callback(dispatch)

        winner = list(seen)[-1]
        assert seen == {11: 3, 22: 1}
        assert get_all_item_owners("RAFFLE") == []
        [reply] = dispatch.sent
        assert reply.content == f"<@{winner}>"                  # in the text, so Discord actually pings them
        assert not reply.ephemeral
        embed = reply.embed
        assert embed.title == "🎟️ Raffle Winner!"
        assert f"Congratulations <@{winner}>! You've won the raffle!" in embed.description
        assert f"Please DM <@{DEFAULT_ADMIN_USER_ID}> with your choice!" in embed.description
        assert embed.footer.text == "Winner drawn from a pool of 4 tickets."

    async def test_the_second_draw_finds_the_pool_empty(self, dispatch, execute):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (11, 'RAFFLE', 1)")
        await draw_raffle.callback(dispatch)
        dispatch.sent.clear()

        await draw_raffle.callback(dispatch)

        assert dispatch.sent[0].content == "Nobody has bought any raffle tickets yet!"

    async def test_other_items_are_not_affected(self, dispatch, execute):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (11, 'RAFFLE', 1), (11, 'BADGE', 2)")

        await draw_raffle.callback(dispatch)

        assert get_all_item_owners("BADGE") == [(11, 2)]

    async def test_the_winner_is_logged(self, dispatch, execute, caplog):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (11, 'RAFFLE', 1)")

        with caplog.at_level(logging.INFO, logger="iu-bot"):
            await draw_raffle.callback(dispatch)

        assert "Raffle winner: 11" in caplog.text
        assert isinstance(dispatch.sent[0].embed, discord.Embed)
