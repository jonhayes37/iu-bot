-- The Award Families (Daesang, Bonsang, Fun)
CREATE TABLE IF NOT EXISTS hma_families (
    family_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

-- The Categories (Linked to Families)
CREATE TABLE IF NOT EXISTS hma_categories (
    category_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    name TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (family_id) REFERENCES hma_families(family_id) ON DELETE CASCADE
);

-- The Nominations (Linked to Categories)
CREATE TABLE IF NOT EXISTS hma_nominations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    award_year INTEGER NOT NULL,
    category_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    nomination_text TEXT NOT NULL,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES hma_categories(category_id) ON DELETE CASCADE
);

-- Seed the Families
INSERT OR IGNORE INTO hma_families (family_id, display_name) VALUES
('daesang', 'Daesang'),
('bonsang', 'Bonsang'),
('fun', 'Fun');

-- Seed the Daesangs
INSERT OR IGNORE INTO hma_categories (category_id, family_id, name, is_active) VALUES
('aoty', 'daesang', 'Album of the Year', 1),
('aroty', 'daesang', 'Artist of the Year', 1),
('soty', 'daesang', 'Song of the Year', 1),
('mvoty', 'daesang', 'Music Video of the Year', 1);

-- Seed the Bonsangs
INSERT OR IGNORE INTO hma_categories (category_id, family_id, name, is_active) VALUES
('best_bg', 'bonsang', 'Best Boy Group', 1),
('best_gg', 'bonsang', 'Best Girl Group', 1),
('best_m_solo', 'bonsang', 'Best Male Soloist', 1),
('best_f_solo', 'bonsang', 'Best Female Soloist', 1),
('best_band', 'bonsang', 'Best Band', 1),
('best_subunit', 'bonsang', 'Best Sub-unit', 1),
('best_collab', 'bonsang', 'Best Collaboration', 1),
('best_bg_choreo', 'bonsang', 'Best Boy Group Choreography', 1),
('best_gg_choreo', 'bonsang', 'Best Girl Group Choreography', 1),
('best_b_track', 'bonsang', 'Best B-Track', 1),
('best_ost', 'bonsang', 'Best OST', 1),
('best_vocal_cover', 'bonsang', 'Best Vocal Cover', 1),
('best_dance_cover', 'bonsang', 'Best Dance Cover', 1),
('best_non_kr', 'bonsang', 'Best Non-Korean Release', 1),
('best_revival', 'bonsang', 'Best Revival', 1),
('best_m_rookie', 'bonsang', 'Best Male Rookie', 1),
('best_f_rookie', 'bonsang', 'Best Female Rookie', 1);

-- Seed the Fun Awards
INSERT OR IGNORE INTO hma_categories (category_id, family_id, name, is_active) VALUES
('meme_cb', 'fun', 'Most Meme-worthy Comeback', 1),
('anime_hair', 'fun', 'Best Anime Hair', 1),
('missed_group', 'fun', 'Most Missed Group', 1),
('concept_change', 'fun', 'Biggest Concept Change', 1),
('crazy_lyric', 'fun', 'Craziest English Lyric', 1),
('unique_mv', 'fun', 'Most Unique Music Video Concept', 1);