-- The Tournament
CREATE TABLE IF NOT EXISTS tournaments (
    tournament_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    days_per_round INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'completed', 'cancelled'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tournament entrants
CREATE TABLE IF NOT EXISTS tournament_entrants (
    entrant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id TEXT NOT NULL,
    name TEXT NOT NULL,
    seed INTEGER NOT NULL,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id) ON DELETE CASCADE
);

-- Individual matches
CREATE TABLE IF NOT EXISTS tournament_matches (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id TEXT NOT NULL,
    round_num INTEGER NOT NULL,
    match_position INTEGER NOT NULL,
    entrant_a_id INTEGER,
    entrant_b_id INTEGER,
    winner_id INTEGER,
    next_match_id INTEGER,
    message_id INTEGER,         -- The Discord ID of the poll message
    end_timestamp TIMESTAMP,    -- When the background task should close it
    FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id) ON DELETE CASCADE,
    FOREIGN KEY (entrant_a_id) REFERENCES tournament_entrants(entrant_id),
    FOREIGN KEY (entrant_b_id) REFERENCES tournament_entrants(entrant_id),
    FOREIGN KEY (winner_id) REFERENCES tournament_entrants(entrant_id)
);

-- The Voting Ledger
CREATE TABLE IF NOT EXISTS tournament_votes (
    match_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    choice_entrant_id INTEGER NOT NULL,
    PRIMARY KEY (match_id, user_id), -- This composite key makes it impossible to vote twice. 
                                     -- Changing a vote just runs an SQL UPDATE on this row.
    FOREIGN KEY (match_id) REFERENCES tournament_matches(match_id) ON DELETE CASCADE
);

-- Reward Ledger (voting in all matchups in a round rewards 1 heart)
CREATE TABLE IF NOT EXISTS tournament_rewards_ledger (
    tournament_id TEXT NOT NULL,
    round_num INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (tournament_id, round_num, user_id), -- The lock
    FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id) ON DELETE CASCADE
);