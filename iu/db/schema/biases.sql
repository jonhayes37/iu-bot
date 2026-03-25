-- Schema for the biases database

-- Table to store ultimate bias information for each user
CREATE TABLE IF NOT EXISTS ultimate_biases (
    user_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    birth_name TEXT NOT NULL,
    birthday TEXT NOT NULL,
    colour INTEGER NOT NULL,
    group_name TEXT NOT NULL,
    hometown TEXT NOT NULL,
    image_filename TEXT NOT NULL,
    position TEXT NOT NULL,
    reason TEXT NOT NULL
);

-- Table to store artist bias information for each user
CREATE TABLE IF NOT EXISTS artist_biases (
    user_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    album TEXT NOT NULL,
    b_track TEXT NOT NULL,
    bias TEXT NOT NULL,
    colour INTEGER NOT NULL,
    debut_date TEXT NOT NULL,
    image_filename TEXT NOT NULL,
    label TEXT NOT NULL,
    members TEXT NOT NULL,
    reason TEXT NOT NULL,
    title_track TEXT NOT NULL
);