-- db/schema/hall_of_fame_nominations.sql

CREATE TABLE IF NOT EXISTS hall_of_fame_nominations (
    user_id INTEGER NOT NULL,
    award_year INTEGER NOT NULL,
    username TEXT NOT NULL,
    nomination_text TEXT NOT NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, award_year)
);

CREATE TABLE IF NOT EXISTS hof_official_nominees (
    award_year INTEGER NOT NULL,
    nominee_name TEXT NOT NULL,
    PRIMARY KEY (award_year, nominee_name)
);

CREATE TABLE IF NOT EXISTS hall_of_fame_votes (
    user_id INTEGER NOT NULL,
    award_year INTEGER NOT NULL,
    first_choice TEXT NOT NULL,
    second_choice TEXT NOT NULL,
    third_choice TEXT NOT NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, award_year)
);