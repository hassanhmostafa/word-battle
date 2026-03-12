-- ============================================================
-- Users Table
-- ============================================================
CREATE TABLE IF NOT EXISTS Users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT UNIQUE NOT NULL,
    username TEXT
);

-- ============================================================
-- Games Table (Full 18-round session)
-- ============================================================
CREATE TABLE IF NOT EXISTS Games (
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

-- ============================================================
-- Rounds Table (One word-guessing challenge)
-- ============================================================
CREATE TABLE IF NOT EXISTS Rounds (
    round_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    secret_word TEXT NOT NULL,
    category TEXT,
    difficulty TEXT,
    game_mode TEXT DEFAULT 'ai_guesses',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    outcome TEXT,
    FOREIGN KEY (game_id) REFERENCES Games(game_id),
    UNIQUE(game_id, round_number)
);

-- ============================================================
-- Actions Table (Individual actions: describe, guess, hint)
-- ============================================================
CREATE TABLE IF NOT EXISTS Actions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    action_number INTEGER NOT NULL,
    actor TEXT NOT NULL,
    action_type TEXT NOT NULL,
    content TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER,
    FOREIGN KEY (round_id) REFERENCES Rounds(round_id),
    UNIQUE(round_id, action_number)
);

-- ============================================================
-- Referee_Checks Table (Validation attempts)
-- ============================================================
CREATE TABLE IF NOT EXISTS Referee_Checks (
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    action_id INTEGER,
    check_type TEXT NOT NULL,
    text_checked TEXT NOT NULL,
    secret_word TEXT NOT NULL,
    is_valid BOOLEAN NOT NULL,
    violation_type TEXT,
    violation_details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (round_id) REFERENCES Rounds(round_id),
    FOREIGN KEY (action_id) REFERENCES Actions(action_id)
);