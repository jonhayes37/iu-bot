PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS list_events (
    event_id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    expected_count INTEGER NOT NULL DEFAULT 0,
    placeholder_text TEXT,
    message_id TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS list_submissions (
    submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    cleaned_text TEXT NOT NULL,
    extracted_urls TEXT,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES list_events (event_id) ON DELETE CASCADE,
    UNIQUE(event_id, user_id)
);