-- db/schema/hall_of_fame_nominations.sql

CREATE TABLE IF NOT EXISTS hall_of_fame_nominations (
    user_id INTEGER NOT NULL,
    award_year INTEGER NOT NULL,
    username TEXT NOT NULL,
    nomination_text TEXT NOT NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, award_year)
);