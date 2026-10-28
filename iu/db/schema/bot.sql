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

-- The end of year posts with buttons (suggestions, nominations, voting), so /end-of-year-close can turn them off
CREATE TABLE IF NOT EXISTS end_of_year_posts (
    message_id INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    award_year INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('suggestions', 'nominations', 'voting')),
    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Awards years whose festivities are over: every end of year button, form and ballot for them refuses
CREATE TABLE IF NOT EXISTS end_of_year_closed (
    award_year INTEGER PRIMARY KEY,
    closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
