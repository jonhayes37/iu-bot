-- schema.sql
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    last_daily_given TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    sender_id TEXT,
    receiver_id INTEGER,
    amount INTEGER,
    reason TEXT,
    message_url TEXT
);

CREATE TABLE IF NOT EXISTS milestone_messages (
    message_id INTEGER PRIMARY KEY,
    author_id INTEGER,
    paid_out BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS merch_items (
    item_id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    price INTEGER,
    max_per_user INTEGER
);

CREATE TABLE IF NOT EXISTS user_inventory (
    user_id INTEGER,
    item_id TEXT,
    quantity_owned INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, item_id)
);