/* ============================================================
   INDEXES for word_game.db
   Run once. Safe to re-run (IF NOT EXISTS).
   ============================================================ */

PRAGMA foreign_keys = ON;

-- Users
-- participant_id already has an index because it's UNIQUE
CREATE INDEX IF NOT EXISTS idx_users_username
ON Users(username);

CREATE INDEX IF NOT EXISTS idx_users_created_at
ON Users(created_at);

-- Games (most analytics + joins start here)
CREATE INDEX IF NOT EXISTS idx_games_user_id
ON Games(user_id);

CREATE INDEX IF NOT EXISTS idx_games_outcome
ON Games(outcome);

CREATE INDEX IF NOT EXISTS idx_games_game_mode
ON Games(game_mode);

CREATE INDEX IF NOT EXISTS idx_games_category
ON Games(category);

CREATE INDEX IF NOT EXISTS idx_games_difficulty
ON Games(difficulty);

CREATE INDEX IF NOT EXISTS idx_games_started_at
ON Games(started_at);

CREATE INDEX IF NOT EXISTS idx_games_ended_at
ON Games(ended_at);

-- Turns (heavy join table)
CREATE INDEX IF NOT EXISTS idx_turns_game_id
ON Turns(game_id);

-- Useful for ordering / fetching the last turn quickly
CREATE INDEX IF NOT EXISTS idx_turns_game_turn_number
ON Turns(game_id, turn_number);

-- Useful for filters like: actor='ai' AND action_type='guess'
CREATE INDEX IF NOT EXISTS idx_turns_actor_action
ON Turns(actor, action_type);

-- Referee_Checks
CREATE INDEX IF NOT EXISTS idx_referee_checks_turn_id
ON Referee_Checks(turn_id);

CREATE INDEX IF NOT EXISTS idx_referee_checks_is_valid
ON Referee_Checks(is_valid);

CREATE INDEX IF NOT EXISTS idx_referee_checks_timestamp
ON Referee_Checks(timestamp);

-- AI_Responses
CREATE INDEX IF NOT EXISTS idx_ai_responses_game_id
ON AI_Responses(game_id);

CREATE INDEX IF NOT EXISTS idx_ai_responses_turn_id
ON AI_Responses(turn_id);

CREATE INDEX IF NOT EXISTS idx_ai_responses_model
ON AI_Responses(model_name);

CREATE INDEX IF NOT EXISTS idx_ai_responses_timestamp
ON AI_Responses(timestamp);


CREATE INDEX IF NOT EXISTS idx_games_user_outcome ON Games(user_id, outcome);
CREATE INDEX IF NOT EXISTS idx_games_mode_diff_cat ON Games(game_mode, difficulty, category);

CREATE INDEX IF NOT EXISTS idx_turns_game_actor_type ON Turns(game_id, actor, action_type);
CREATE INDEX IF NOT EXISTS idx_turns_game_turnnum ON Turns(game_id, turn_number);

CREATE INDEX IF NOT EXISTS idx_refchecks_turn_valid ON Referee_Checks(turn_id, is_valid);
CREATE INDEX IF NOT EXISTS idx_refchecks_timestamp ON Referee_Checks(timestamp);

CREATE INDEX IF NOT EXISTS idx_airesponses_game_turn ON AI_Responses(game_id, turn_id);