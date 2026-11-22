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

-- Everyone inducted so far, shown on the nominations form so members don't nominate them again.
-- A name is in the Hall of Fame once (compared ignoring capitalisation).
CREATE TABLE IF NOT EXISTS hall_of_famers (
    name TEXT NOT NULL COLLATE NOCASE PRIMARY KEY,
    year_inducted INTEGER NOT NULL
);

-- Lifetime achievement awards, chosen by the admin (not voted on).
CREATE TABLE IF NOT EXISTS lifetime_achievers (
    name TEXT NOT NULL COLLATE NOCASE PRIMARY KEY,
    year_inducted INTEGER NOT NULL
);

-- Inductees from before /add-hall-of-famer and /add-lifetime-achiever existed. This file runs on every
-- startup, so the inserts skip names already there (a seeded row deleted by hand comes back on restart).
INSERT OR IGNORE INTO hall_of_famers (name, year_inducted) VALUES
    ('BoA', 2020), ('BTS', 2020), ('Girls'' Generation', 2020),
    ('SHINee', 2021), ('KARA', 2021), ('Bigbang', 2021),
    ('Twice', 2022), ('IU', 2022), ('Psy', 2022),
    ('2NE1', 2023), ('Blackpink', 2023), ('Seventeen', 2023),
    ('Red Velvet', 2024), ('Shinsadong Tiger', 2024), ('4Minute', 2024),
    ('GFriend', 2025), ('JYP', 2025), ('Kenzie', 2025);

INSERT OR IGNORE INTO lifetime_achievers (name, year_inducted) VALUES
    ('IU', 2020),
    ('Psy', 2021),
    ('JYP', 2022),
    ('Min Hee Jin', 2023),
    ('Shinsadong Tiger', 2024),
    ('Teddy', 2025);
