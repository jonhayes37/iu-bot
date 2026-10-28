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

-- Secret polls: members vote with buttons, nobody sees the count, and the results are sent only to the
-- admin who started the poll
CREATE TABLE IF NOT EXISTS secret_polls (
    poll_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,                     -- set once the poll is posted
    closes_at TIMESTAMP NOT NULL,           -- UTC, "YYYY-MM-DD HH:MM:SS"
    closed INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS secret_poll_options (
    poll_id INTEGER NOT NULL,
    position INTEGER NOT NULL,              -- 0 for the first option
    label TEXT NOT NULL,
    PRIMARY KEY (poll_id, position),
    FOREIGN KEY (poll_id) REFERENCES secret_polls(poll_id) ON DELETE CASCADE
);

-- One vote per member per poll; voting again replaces it
CREATE TABLE IF NOT EXISTS secret_poll_votes (
    poll_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (poll_id, user_id),
    FOREIGN KEY (poll_id, position) REFERENCES secret_poll_options(poll_id, position) ON DELETE CASCADE
);
