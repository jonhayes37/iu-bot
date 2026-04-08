CREATE TABLE IF NOT EXISTS eoy_top_songs (
    user_id INTEGER NOT NULL,
    award_year INTEGER NOT NULL,
    username TEXT NOT NULL,
    top_25_raw TEXT NOT NULL,
    top_25_clean TEXT NOT NULL,
    top_25_urls TEXT,
    hms_raw TEXT,
    hms_clean TEXT,
    hms_urls TEXT,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, award_year)
);