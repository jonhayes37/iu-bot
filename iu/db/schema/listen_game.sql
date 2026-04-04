-- Tracks the overarching game instances
CREATE TABLE IF NOT EXISTS listen_games (
    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
    gm_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    max_round_days INTEGER DEFAULT NULL
);

-- Tracks the players, their turn order, and scores for a specific game
CREATE TABLE IF NOT EXISTS listen_players (
    game_id INTEGER,
    user_id INTEGER,
    turn_order INTEGER,
    score INTEGER DEFAULT 0,
    last_reminded_at DATETIME DEFAULT NULL,
    PRIMARY KEY (game_id, user_id),
    FOREIGN KEY (game_id) REFERENCES listen_games(game_id) ON DELETE CASCADE
);

-- Tracks the rounds within a specific game
CREATE TABLE IF NOT EXISTS listen_rounds (
    round_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER,
    host_id INTEGER, 
    theme TEXT,
    playlist_id TEXT, 
    status TEXT, 
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status_message_id INTEGER DEFAULT NULL,
    FOREIGN KEY (game_id) REFERENCES listen_games(game_id) ON DELETE CASCADE
);

-- Tracks the songs submitted to a specific round
CREATE TABLE IF NOT EXISTS listen_submissions (
    round_id INTEGER,
    user_id INTEGER,
    video_id TEXT NOT NULL, 
    raw_title TEXT NOT NULL,
    clean_title TEXT NOT NULL,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    rank INTEGER DEFAULT NULL,
    points_awarded INTEGER DEFAULT 0,
    commentary TEXT DEFAULT NULL,
    PRIMARY KEY (round_id, user_id),
    FOREIGN KEY (round_id) REFERENCES listen_rounds(round_id) ON DELETE CASCADE
);