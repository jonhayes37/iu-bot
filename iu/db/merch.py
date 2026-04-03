"""db/merch.py"""
from datetime import datetime
import os
import zoneinfo
import sqlite3

DB_PATH_MERCH = os.getenv('DB_PATH_MERCH')

def ensure_users_exist(cursor: sqlite3.Cursor, *user_ids):
    """
    Takes an active database cursor and an arbitrary number of user IDs.
    Ensures each user exists in the users table with a default balance of 0.
    """
    for user_id in user_ids:
        # Only insert actual Discord IDs (integers), ignoring 'SYSTEM' or 'MERCH'
        if isinstance(user_id, int):
            cursor.execute(
                "INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", 
                (user_id,)
            )

# Process a daily heart gift from sender_id to receiver_id,
# with an optional message URL for logging.
def process_daily_heart(sender_id: int, receiver_id: int, message_url: str) -> bool:
    """
    Attempts to process a daily heart transaction. 
    Returns True if successful, False if the user already gave a heart today.
    """
    # Get the current date in EST/EDT
    est_zone = zoneinfo.ZoneInfo("America/New_York")
    current_date_str = str(datetime.now(est_zone).date())

    with sqlite3.connect(DB_PATH_MERCH) as conn:
        cursor = conn.cursor()

        # Check if the sender has already given a heart today
        cursor.execute("SELECT last_daily_given FROM users WHERE user_id = ?", (sender_id,))
        row = cursor.fetchone()

        if row and row[0] == current_date_str:
            return False  # Cooldown active; they already gave one today

        ensure_users_exist(cursor, sender_id, receiver_id)

        # Update the sender's cooldown date
        cursor.execute("UPDATE users SET last_daily_given = ? WHERE user_id = ?", (current_date_str, sender_id))

        # Give the receiver 1 heart (heart)
        cursor.execute("UPDATE users SET balance = balance + 1 WHERE user_id = ?", (receiver_id,))

        # Log it in the transactions ledger
        cursor.execute("""
            INSERT INTO transactions (sender_id, receiver_id, amount, reason, message_url)
            VALUES (?, ?, 1, 'Daily cheer given', ?)
        """, (str(sender_id), receiver_id, message_url))

        conn.commit()
        return True

# Processes a message with 5 or more unique people reacting
def process_milestone_award(message_id: int, author_id: int, message_url: str) -> bool:
    """Checks the state table and awards 3 hearts if not already paid."""
    with sqlite3.connect(DB_PATH_MERCH) as conn:
        cursor = conn.cursor()

        # Check idempotency table to prevent duplicate payouts
        cursor.execute("SELECT paid_out FROM milestone_messages WHERE message_id = ?", (message_id,))
        if cursor.fetchone():
            return False

        ensure_users_exist(cursor, author_id)

        # Mark this message as paid
        cursor.execute("INSERT INTO milestone_messages (message_id, author_id, paid_out) VALUES (?, ?, 1)",
                       (message_id, author_id))

        # Add 3 hearts
        cursor.execute("UPDATE users SET balance = balance + 3 WHERE user_id = ?", (author_id,))

        # Log the transaction
        cursor.execute("""
            INSERT INTO transactions (sender_id, receiver_id, amount, reason, message_url)
            VALUES ('SYSTEM', ?, 3, 'Milestone: 5 reactions', ?)
        """, (author_id, message_url))

        conn.commit()
        return True


def modify_db_balance(admin_id: int, target_id: int, amount: int, reason: str):
    """Executes the SQLite transaction to modify a user's balance."""
    with sqlite3.connect(DB_PATH_MERCH) as conn:
        cursor = conn.cursor()

        # Ensure the target user is in the database
        ensure_users_exist(cursor, target_id)

        # Update their balance
        cursor.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?", 
            (amount, target_id)
        )

        # Log the admin transaction
        cursor.execute("""
            INSERT INTO transactions (sender_id, receiver_id, amount, reason, message_url)
            VALUES (?, ?, ?, ?, NULL)
        """, (f"ADMIN:{admin_id}", target_id, amount, reason))

        conn.commit()

# Add this above your Discord command functions
def upsert_merch_item(item_id: str, name: str, description: str, price: int, max_per_user: int = None):
    """Inserts a new merch item, or updates it if the item_id already exists."""
    with sqlite3.connect(DB_PATH_MERCH) as conn:
        cursor = conn.cursor()
        # Using SQLite's UPSERT syntax
        cursor.execute("""
            INSERT INTO merch_items (item_id, name, description, price, max_per_user)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                price=excluded.price,
                max_per_user=excluded.max_per_user
        """, (item_id.upper(), name, description, price, max_per_user))
        conn.commit()


def get_user_balance(user_id: int) -> int:
    """Fetches a user's heart balance. Returns 0 if they don't exist yet."""
    with sqlite3.connect(DB_PATH_MERCH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        if row:
            return row[0]
        return 0


def get_user_merch_catalog(user_id: int):
    """Fetches the merch catalog and joins it with the user's current inventory."""
    with sqlite3.connect(DB_PATH_MERCH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                s.item_id, 
                s.name, 
                s.description, 
                s.price, 
                s.max_per_user,
                COALESCE(i.quantity_owned, 0) as quantity_owned
            FROM merch_items s
            LEFT JOIN user_inventory i ON s.item_id = i.item_id AND i.user_id = ?
            ORDER BY s.price ASC
        """, (user_id,))
        return cursor.fetchall()


def process_purchase(user_id: int, item_id: str) -> tuple[bool, str]:
    """
    Validates and executes a merch booth purchase atomically.
    Returns (success_boolean, user_message).
    """
    clean_item_id = item_id.upper()

    with sqlite3.connect(DB_PATH_MERCH) as conn:
        cursor = conn.cursor()
        ensure_users_exist(cursor, user_id)

        # Check if the item exists in the catalog
        cursor.execute("SELECT name, price, max_per_user FROM merch_items WHERE item_id = ?", (clean_item_id,))
        item = cursor.fetchone()

        if not item:
            return False, f"Could not find an item with SKU `{clean_item_id}` in the merch booth!"

        name, price, max_per_user = item

        # Check heart balance
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = cursor.fetchone()[0]

        if balance < price:
            return False, f"You don't have enough hearts! You need **{price}**, but you only have **{balance}**."

        # Check inventory limits
        cursor.execute("SELECT quantity_owned FROM user_inventory WHERE user_id = ? AND item_id = ?",
                       (user_id, clean_item_id))
        inv = cursor.fetchone()
        quantity_owned = inv[0] if inv else 0

        if max_per_user is not None and quantity_owned >= max_per_user:
            return False, "You've already reached the maximum limit " \
                f"({max_per_user}) for **{name}**!"

        # Execute the transaction - deduct hearts, add to inventory, and log
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
        cursor.execute("""
            INSERT INTO user_inventory (user_id, item_id, quantity_owned) 
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, item_id) DO UPDATE SET quantity_owned = quantity_owned + 1
        """, (user_id, clean_item_id))
        cursor.execute("""
            INSERT INTO transactions (sender_id, receiver_id, amount, reason, message_url)
            VALUES ('SHOP', ?, ?, ?, NULL)
        """, (user_id, -price, f"Purchased {name} ({clean_item_id})"))

        conn.commit()
        return True, f"Successfully purchased **{name}** for {price} hearts!"


def get_user_inventory(user_id: int):
    """Fetches a user's purchased items by joining inventory with the catalog."""
    with sqlite3.connect(DB_PATH_MERCH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.name, m.item_id, m.description, u.quantity_owned
            FROM user_inventory u
            JOIN merch_items m ON u.item_id = m.item_id
            WHERE u.user_id = ? AND u.quantity_owned > 0
            ORDER BY m.name ASC
        """, (user_id,))
        return cursor.fetchall()

def reset_item_inventory(item_id: str) -> int:
    """
    Deletes all inventory records for a specific item, effectively resetting everyone to 0.
    Returns the number of users who had their inventory cleared.
    """
    clean_item_id = item_id.upper()
    with sqlite3.connect(DB_PATH_MERCH) as conn:
        cursor = conn.cursor()

        # Delete all records of this item from user_inventory
        cursor.execute("DELETE FROM user_inventory WHERE item_id = ?", (clean_item_id,))
        rows_affected = cursor.rowcount

        conn.commit()
        return rows_affected

def get_all_item_owners(item_id: str) -> list[tuple[int, int]]:
    """Fetches all users who own a specific item and their quantities."""
    clean_item_id = item_id.upper()
    with sqlite3.connect(DB_PATH_MERCH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, quantity_owned 
            FROM user_inventory 
            WHERE item_id = ? AND quantity_owned > 0
        """, (clean_item_id,))
        return cursor.fetchall()
