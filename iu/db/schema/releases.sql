-- releases_schema.sql

-- Tracks the actual YouTube playlists (e.g., "2026 K-Pop Releases")
CREATE TABLE IF NOT EXISTS youtube_playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,           -- e.g., 2026
    playlist_id TEXT UNIQUE NOT NULL -- The actual YouTube Playlist ID (e.g., PLabc123...)
);

-- Tracks individual K-Pop releases posted in the Discord channel
CREATE TABLE IF NOT EXISTS new_releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT UNIQUE NOT NULL,    -- Extracted YouTube ID (e.g., dQw4w9WgXcQ)
    original_url TEXT NOT NULL,       -- The raw link posted in Discord
    message_id TEXT UNIQUE NOT NULL,  -- Discord message ID (prevents duplicate parsing)
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
    processed BOOLEAN DEFAULT 0       -- 0 = pending (False), 1 = added to YT (True)
);

-- Indexes to make your daily batching and fallback commands lightning fast
CREATE INDEX IF NOT EXISTS idx_unprocessed_releases ON new_releases(processed);
CREATE INDEX IF NOT EXISTS idx_video_id ON new_releases(video_id);