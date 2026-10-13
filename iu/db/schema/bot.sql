CREATE TABLE IF NOT EXISTS statuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status_text TEXT NOT NULL,
    max_duration_days INTEGER NOT NULL DEFAULT 7,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scheduled events whose 15-minute reminder thread has been posted, so a restart doesn't post it again
CREATE TABLE IF NOT EXISTS notified_events (
    event_id INTEGER PRIMARY KEY,
    notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
