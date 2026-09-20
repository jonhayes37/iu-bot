"""Tests for db/merch.py: hearts, the daily cheer, milestones and the Merch Booth."""

import threading

import pytest

from config import Database
from db.connection import db_connection
from db.merch import (
    check_user_owns_item, credit_hearts, ensure_users_exist, get_all_item_owners, get_award_recipient,
    get_user_balance, get_user_inventory, get_user_merch_catalog, is_milestone_paid, modify_db_balance,
    process_daily_heart, process_milestone_award, process_purchase, reset_item_inventory, upsert_merch_item,
    use_up_item
)

URL = "https://discord.com/channels/1/2/3"


@pytest.fixture(autouse=True)
def _merch_database(databases):
    databases(Database.MERCH)


def _give(execute, user_id, balance):
    execute(Database.MERCH, "INSERT OR REPLACE INTO users (user_id, balance) VALUES (?, ?)", user_id, balance)


def _transactions(query):
    return query(Database.MERCH, "SELECT * FROM transactions ORDER BY id")


class TestEnsureUsersExist:
    """New members start with a zero balance the first time they are involved in a transaction."""

    def test_creates_missing_users_with_zero_hearts(self, query):
        with db_connection(Database.MERCH) as conn:
            ensure_users_exist(conn.cursor(), 1, 2)

        assert [(r["user_id"], r["balance"]) for r in query(Database.MERCH, "SELECT * FROM users ORDER BY user_id")] \
            == [(1, 0), (2, 0)]

    def test_leaves_an_existing_balance_alone(self, execute, query):
        _give(execute, 1, 40)

        with db_connection(Database.MERCH) as conn:
            ensure_users_exist(conn.cursor(), 1)

        assert query(Database.MERCH, "SELECT balance FROM users")[0]["balance"] == 40

    def test_ignores_ids_that_are_not_members(self, query):
        # 'SYSTEM' and 'ADMIN:...' style senders are strings, not Discord IDs
        with db_connection(Database.MERCH) as conn:
            ensure_users_exist(conn.cursor(), "SYSTEM", "MERCH", 5)

        assert [r["user_id"] for r in query(Database.MERCH, "SELECT user_id FROM users")] == [5]


class TestBalances:
    """get_user_balance, modify_db_balance and credit_hearts."""

    def test_unknown_user_has_zero(self):
        assert get_user_balance(99) == 0

    def test_reading_a_balance_does_not_create_the_user(self, query):
        get_user_balance(99)

        assert query(Database.MERCH, "SELECT * FROM users") == []

    def test_adding_hearts_creates_the_user_and_records_who_did_it(self, query):
        modify_db_balance(admin_id=7, target_id=1, amount=25, reason="Contest winner")

        assert get_user_balance(1) == 25
        [tx] = _transactions(query)
        assert (tx["sender_id"], tx["receiver_id"], tx["amount"], tx["reason"], tx["message_url"]) == \
            ("ADMIN:7", 1, 25, "Contest winner", None)

    def test_hearts_can_be_taken_away(self, execute):
        _give(execute, 1, 30)

        modify_db_balance(7, 1, -10, "Correction")

        assert get_user_balance(1) == 20

    def test_amounts_accumulate(self):
        modify_db_balance(7, 1, 5, "a")
        modify_db_balance(7, 1, 5, "b")

        assert get_user_balance(1) == 10

    def test_credit_hearts_works_inside_a_larger_transaction(self, query):
        with pytest.raises(RuntimeError):
            with db_connection(Database.MERCH) as conn:
                credit_hearts(conn, "SYSTEM", 1, 50, "Reward")
                raise RuntimeError("something later in the transaction failed")

        assert get_user_balance(1) == 0
        assert _transactions(query) == []

    def test_credit_hearts_can_target_an_attached_merch_database(self, databases, query):
        databases(Database.MERCH, Database.LISTS)

        with db_connection(Database.LISTS, attach=(Database.MERCH,)) as conn:
            credit_hearts(conn, "SYSTEM", 1, 50, "Reward", schema="merch.")

        assert get_user_balance(1) == 50
        assert _transactions(query)[0]["sender_id"] == "ADMIN:SYSTEM"


class TestGetAwardRecipient:
    """Awards carry a marker in their reason so they are never paid twice."""

    def test_nobody_before_it_is_paid(self):
        assert get_award_recipient("[raffle:abc123]") is None

    def test_finds_who_was_paid(self):
        modify_db_balance(7, 42, 100, "Raffle winner [raffle:abc123]")

        assert get_award_recipient("[raffle:abc123]") == 42

    def test_a_different_marker_is_not_a_match(self):
        modify_db_balance(7, 42, 100, "Raffle winner [raffle:abc123]")

        assert get_award_recipient("[raffle:zzz999]") is None

    def test_the_marker_is_matched_as_plain_text(self):
        # LIKE would treat % and _ as wildcards; this must not
        modify_db_balance(7, 42, 100, "Award [x:1]")

        assert get_award_recipient("%") is None
        assert get_award_recipient("[x:_]") is None


class TestProcessDailyHeart:
    """Each member can give one heart a day, and the day rolls over at midnight Eastern."""

    def test_the_first_heart_of_the_day_moves_one_heart(self, frozen_time, query):
        frozen_time("2026-03-17 15:00:00")

        assert process_daily_heart(1, 2, URL) is True

        assert get_user_balance(2) == 1
        assert get_user_balance(1) == 0
        [tx] = _transactions(query)
        assert (tx["sender_id"], tx["receiver_id"], tx["amount"], tx["reason"], tx["message_url"]) == \
            ("1", 2, 1, "Daily cheer given", URL)

    def test_a_second_heart_the_same_day_is_refused(self, frozen_time, query):
        frozen_time("2026-03-17 15:00:00")
        process_daily_heart(1, 2, URL)

        assert process_daily_heart(1, 3, URL) is False

        assert get_user_balance(3) == 0
        assert len(_transactions(query)) == 1

    def test_the_refusal_is_per_giver(self, frozen_time):
        frozen_time("2026-03-17 15:00:00")
        process_daily_heart(1, 3, URL)

        assert process_daily_heart(2, 3, URL) is True
        assert get_user_balance(3) == 2

    def test_the_next_day_they_can_give_again(self, frozen_time):
        frozen_time("2026-03-17 15:00:00")
        process_daily_heart(1, 2, URL)
        frozen_time("2026-03-18 15:00:00")

        assert process_daily_heart(1, 2, URL) is True
        assert get_user_balance(2) == 2

    def test_the_day_rolls_over_at_midnight_eastern_not_utc(self, frozen_time):
        # In March Eastern is UTC-4, so midnight is 04:00 UTC
        frozen_time("2026-03-17 20:00:00")
        process_daily_heart(1, 2, URL)

        frozen_time("2026-03-18 03:59:59")   # 23:59:59 Eastern, still March 17
        assert process_daily_heart(1, 2, URL) is False

        frozen_time("2026-03-18 04:00:00")   # midnight Eastern
        assert process_daily_heart(1, 2, URL) is True

    def test_two_reactions_at_once_give_only_one_heart(self, frozen_time):
        frozen_time("2026-03-17 15:00:00")
        ensure = threading.Barrier(2)
        results = []

        def react(receiver):
            ensure.wait()
            results.append(process_daily_heart(1, receiver, URL))

        threads = [threading.Thread(target=react, args=(receiver,)) for receiver in (2, 3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(results) == [False, True]
        assert get_user_balance(2) + get_user_balance(3) == 1


class TestMilestoneAward:
    """A message that gets 5 reactions pays its author 3 hearts, once."""

    def test_pays_the_author_three_hearts_and_logs_it(self, query):
        assert process_milestone_award(500, 1, URL) is True

        assert get_user_balance(1) == 3
        [tx] = _transactions(query)
        assert (tx["sender_id"], tx["receiver_id"], tx["amount"], tx["reason"], tx["message_url"]) == \
            ("SYSTEM", 1, 3, "Milestone: 5 reactions", URL)

    def test_is_never_paid_twice_for_the_same_message(self, query):
        process_milestone_award(500, 1, URL)

        assert process_milestone_award(500, 1, URL) is False

        assert get_user_balance(1) == 3
        assert len(_transactions(query)) == 1

    def test_different_messages_each_pay(self):
        process_milestone_award(500, 1, URL)
        process_milestone_award(501, 1, URL)

        assert get_user_balance(1) == 6

    def test_is_milestone_paid(self):
        assert is_milestone_paid(500) is False

        process_milestone_award(500, 1, URL)

        assert is_milestone_paid(500) is True
        assert is_milestone_paid(501) is False

    def test_two_requests_at_once_pay_only_once(self):
        gate = threading.Barrier(2)
        results = []

        def award():
            gate.wait()
            results.append(process_milestone_award(500, 1, URL))

        threads = [threading.Thread(target=award) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(results) == [False, True]
        assert get_user_balance(1) == 3


class TestUpsertMerchItem:
    """Creating and editing Merch Booth items."""

    def test_creates_an_item_with_an_uppercase_code(self, query):
        upsert_merch_item("sticker", "Sticker", "A sticker", 25, 3)

        row = query(Database.MERCH, "SELECT * FROM merch_items")[0]
        assert (row["item_id"], row["name"], row["description"], row["price"], row["max_per_user"]) == \
            ("STICKER", "Sticker", "A sticker", 25, 3)

    def test_the_same_code_in_any_case_updates_the_item(self, query):
        upsert_merch_item("sticker", "Sticker", "A sticker", 25, 3)

        upsert_merch_item("STICKER", "Big Sticker", "Bigger", 40, None)

        rows = query(Database.MERCH, "SELECT * FROM merch_items")
        assert len(rows) == 1
        assert (rows[0]["name"], rows[0]["price"], rows[0]["max_per_user"]) == ("Big Sticker", 40, None)

    def test_updating_an_item_keeps_what_people_already_own(self, execute, query):
        upsert_merch_item("STICKER", "Sticker", "d", 25, 3)
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (1, 'STICKER', 2)")

        upsert_merch_item("STICKER", "Sticker v2", "d", 30, 3)

        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 2

    @pytest.mark.parametrize("limit", [None, 0, -1, -50])
    def test_no_positive_limit_means_unlimited(self, limit, query):
        # 0 used to be stored as-is, which made the item impossible to buy
        upsert_merch_item("STICKER", "Sticker", "d", 25, limit)

        assert query(Database.MERCH, "SELECT max_per_user FROM merch_items")[0]["max_per_user"] is None

    def test_a_limit_of_one_is_kept(self, query):
        upsert_merch_item("STICKER", "Sticker", "d", 25, 1)

        assert query(Database.MERCH, "SELECT max_per_user FROM merch_items")[0]["max_per_user"] == 1


class TestCatalog:
    """get_user_merch_catalog lists every item with how many the user owns, cheapest first."""

    def test_empty_catalog(self):
        assert get_user_merch_catalog(1) == []

    def test_lists_items_by_price_with_the_users_quantity(self, execute):
        upsert_merch_item("BIG", "Big", "d", 100, None)
        upsert_merch_item("SMALL", "Small", "d", 10, 2)
        execute(Database.MERCH, "INSERT INTO user_inventory (user_id, item_id, quantity_owned) VALUES (1, 'SMALL', 1)")

        catalog = get_user_merch_catalog(1)

        assert catalog == [("SMALL", "Small", "d", 10, 2, 1), ("BIG", "Big", "d", 100, None, 0)]

    def test_other_users_quantities_are_not_shown(self, execute):
        upsert_merch_item("SMALL", "Small", "d", 10, None)
        execute(Database.MERCH, "INSERT INTO user_inventory (user_id, item_id, quantity_owned) VALUES (2, 'SMALL', 5)")

        assert get_user_merch_catalog(1)[0][5] == 0


class TestProcessPurchase:
    """Buying an item checks the item, the balance and the per-user limit, then does everything at once."""

    def test_a_purchase_takes_hearts_adds_the_item_and_logs_it(self, execute, query):
        upsert_merch_item("STICKER", "Sticker", "d", 25, None)
        _give(execute, 1, 100)

        success, message = process_purchase(1, "STICKER")

        assert success is True
        assert message == "Successfully purchased **Sticker** for 25 hearts!"
        assert get_user_balance(1) == 75
        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 1
        [tx] = _transactions(query)
        assert (tx["sender_id"], tx["receiver_id"], tx["amount"], tx["reason"]) == \
            ("SHOP", 1, -25, "Purchased Sticker (STICKER)")

    def test_the_item_code_is_case_insensitive(self, execute):
        upsert_merch_item("STICKER", "Sticker", "d", 25, None)
        _give(execute, 1, 100)

        assert process_purchase(1, "sticker")[0] is True

    def test_buying_again_adds_to_the_quantity(self, execute, query):
        upsert_merch_item("STICKER", "Sticker", "d", 25, None)
        _give(execute, 1, 100)

        process_purchase(1, "STICKER")
        process_purchase(1, "STICKER")

        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 2
        assert get_user_balance(1) == 50

    def test_an_unknown_item_is_refused(self, execute):
        _give(execute, 1, 100)

        success, message = process_purchase(1, "nope")

        assert success is False
        assert message == "Could not find an item with SKU `NOPE` in the merch booth!"
        assert get_user_balance(1) == 100

    def test_not_enough_hearts_is_refused_and_says_how_many(self, execute, query):
        upsert_merch_item("STICKER", "Sticker", "d", 25, None)
        _give(execute, 1, 10)

        success, message = process_purchase(1, "STICKER")

        assert success is False
        assert message == "You don't have enough hearts! You need **25**, but you only have **10**."
        assert get_user_balance(1) == 10
        assert _transactions(query) == []

    def test_exactly_enough_hearts_is_enough(self, execute):
        upsert_merch_item("STICKER", "Sticker", "d", 25, None)
        _give(execute, 1, 25)

        assert process_purchase(1, "STICKER")[0] is True
        assert get_user_balance(1) == 0

    def test_the_per_user_limit_is_enforced(self, execute):
        upsert_merch_item("BADGE", "Badge", "d", 5, 2)
        _give(execute, 1, 100)
        process_purchase(1, "BADGE")
        process_purchase(1, "BADGE")

        success, message = process_purchase(1, "BADGE")

        assert success is False
        assert message == "You've already reached the maximum limit (2) for **Badge**!"
        assert get_user_balance(1) == 90

    def test_the_limit_applies_per_person(self, execute):
        upsert_merch_item("BADGE", "Badge", "d", 5, 1)
        _give(execute, 1, 100)
        _give(execute, 2, 100)
        process_purchase(1, "BADGE")

        assert process_purchase(2, "BADGE")[0] is True

    def test_a_new_user_with_no_hearts_cannot_buy_and_is_created(self, query):
        upsert_merch_item("STICKER", "Sticker", "d", 25, None)

        success, _ = process_purchase(1, "STICKER")

        assert success is False
        assert query(Database.MERCH, "SELECT balance FROM users")[0]["balance"] == 0


class TestInventory:
    """What people own, and the admin tools that read or reset it."""

    @pytest.fixture(autouse=True)
    def _items(self):
        upsert_merch_item("RAFFLE", "Raffle Ticket", "A ticket", 10, None)
        upsert_merch_item("BADGE", "Badge", "A badge", 5, None)

    def test_a_users_inventory_lists_items_by_name(self, execute):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (1, 'RAFFLE', 3), (1, 'BADGE', 1)")

        assert get_user_inventory(1) == [("Badge", "BADGE", "A badge", 1), ("Raffle Ticket", "RAFFLE", "A ticket", 3)]

    def test_items_with_none_left_are_hidden(self, execute):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (1, 'RAFFLE', 0)")

        assert get_user_inventory(1) == []

    def test_check_user_owns_item(self, execute):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (1, 'RAFFLE', 2), (2, 'RAFFLE', 0)")

        assert check_user_owns_item(1, "raffle") is True
        assert check_user_owns_item(2, "RAFFLE") is False
        assert check_user_owns_item(3, "RAFFLE") is False
        assert check_user_owns_item(1, "BADGE") is False

    def test_all_owners_of_an_item(self, execute):
        execute(Database.MERCH,
                "INSERT INTO user_inventory VALUES (1, 'RAFFLE', 2), (2, 'RAFFLE', 0), (3, 'RAFFLE', 1)")

        assert sorted(get_all_item_owners("raffle")) == [(1, 2), (3, 1)]

    def test_resetting_an_item_clears_everyone_and_counts_them(self, execute, query):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (1, 'RAFFLE', 2), (2, 'RAFFLE', 1), (1, 'BADGE', 1)")

        assert reset_item_inventory("raffle") == 2

        assert get_all_item_owners("RAFFLE") == []
        assert query(Database.MERCH, "SELECT item_id FROM user_inventory")[0]["item_id"] == "BADGE"

    def test_resetting_an_item_nobody_owns_is_zero(self):
        assert reset_item_inventory("RAFFLE") == 0


class TestUseUpItem:
    """use_up_item spends one of a user's items inside a transaction the caller controls."""

    @pytest.fixture(autouse=True)
    def _owned(self, execute):
        execute(Database.MERCH, "INSERT INTO user_inventory VALUES (1, 'WAYLT', 2)")

    def test_uses_one_and_reports_it(self, query):
        with db_connection(Database.MERCH) as conn:
            assert use_up_item(conn, 1, "waylt") is True

        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 1

    def test_the_last_one_removes_the_row(self, query):
        with db_connection(Database.MERCH) as conn:
            use_up_item(conn, 1, "WAYLT")
            use_up_item(conn, 1, "WAYLT")

        assert query(Database.MERCH, "SELECT * FROM user_inventory") == []

    def test_having_none_changes_nothing_and_is_false(self, query):
        with db_connection(Database.MERCH) as conn:
            assert use_up_item(conn, 2, "WAYLT") is False
            assert use_up_item(conn, 1, "OTHER") is False

        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 2

    def test_is_undone_if_the_surrounding_transaction_fails(self, query):
        with pytest.raises(RuntimeError):
            with db_connection(Database.MERCH) as conn:
                use_up_item(conn, 1, "WAYLT")
                raise RuntimeError("the rest of the save failed")

        assert query(Database.MERCH, "SELECT quantity_owned FROM user_inventory")[0]["quantity_owned"] == 2
