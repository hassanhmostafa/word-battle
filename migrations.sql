-- ============================================================
-- Migration: Fix default difficulty value from 'easy' to 'easy1'
-- ============================================================
-- Run this AFTER migration_games_rename.sql if you already ran it
-- and the Games table now has current_difficulty DEFAULT 'easy'.
-- This updates both the column default AND any existing rows
-- that were inserted with the old 'easy' value.
-- ============================================================

PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

-- 1. Recreate Games table with correct DEFAULT 'easy1'
CREATE TABLE Games_new (
    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username_at_game_time TEXT,
    current_difficulty TEXT DEFAULT 'easy1',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    outcome TEXT,
    total_rounds INTEGER DEFAULT 0,
    user_final_time INTEGER,
    ai_final_time INTEGER,
    winner TEXT,
    FOREIGN KEY (user_id) REFERENCES Users(user_id)
);

-- 2. Copy data, mapping legacy 'easy' → 'easy1' for any existing rows
INSERT INTO Games_new (
    game_id, user_id, username_at_game_time,
    current_difficulty, started_at, ended_at,
    outcome, total_rounds, user_final_time, ai_final_time, winner
)
SELECT
    game_id, user_id, username_at_game_time,
    CASE current_difficulty
        WHEN 'easy'   THEN 'easy1'
        WHEN 'medium' THEN 'medium1'
        WHEN 'hard'   THEN 'hard1'
        ELSE current_difficulty
    END,
    started_at, ended_at,
    outcome, total_rounds, user_final_time, ai_final_time, winner
FROM Games;

-- 3. Swap tables
DROP TABLE Games;
ALTER TABLE Games_new RENAME TO Games;

-- 4. Recreate indexes
CREATE INDEX IF NOT EXISTS idx_games_user       ON Games(user_id);
CREATE INDEX IF NOT EXISTS idx_games_difficulty ON Games(current_difficulty);

COMMIT;

PRAGMA foreign_keys = ON;
