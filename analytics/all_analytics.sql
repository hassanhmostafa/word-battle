-- ============================================================================
-- ANALYTICS QUERIES FOR NEW SCHEMA (Games + Rounds + Actions)
-- ============================================================================
-- New terminology:
-- - GAME = Full 18-round session (was Sessions)
-- - ROUND = One word-guessing challenge (was Games)
-- - ACTION = Individual action (was Turns)
-- ============================================================================


-- ============================================================================
-- 1) GAME-LEVEL ANALYTICS (Full 18-round sessions)
-- ============================================================================

-- 1A) Game completion rate per user
SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id) AS username,
  COUNT(g.game_id) AS total_games,
  SUM(CASE WHEN g.outcome = 'completed' THEN 1 ELSE 0 END) AS games_completed,
  SUM(CASE WHEN g.outcome = 'quit' THEN 1 ELSE 0 END) AS games_quit,
  SUM(CASE WHEN g.outcome = 'timeout' THEN 1 ELSE 0 END) AS games_timeout,
  ROUND(100.0 * SUM(CASE WHEN g.outcome = 'completed' THEN 1 ELSE 0 END) / COUNT(g.game_id), 2) AS completion_rate_pct
FROM Users u
LEFT JOIN Games g ON g.user_id = u.user_id
GROUP BY u.user_id, username
ORDER BY completion_rate_pct DESC, total_games DESC;


-- 1B) Average rounds completed per game, file: analytics/average_rounds_completed_per_game.sql
-- This shows how many rounds (out of 18) players complete on average before quitting or timing out, broken down by difficulty. It gives insight into how engaging or challenging each difficulty level is
SELECT
  g.current_difficulty_level,
  COUNT(g.game_id) AS total_games,
  ROUND(AVG(g.total_rounds_completed), 2) AS avg_rounds_completed,
  ROUND(MIN(g.total_rounds_completed), 2) AS min_rounds,
  ROUND(MAX(g.total_rounds_completed), 2) AS max_rounds
FROM Games g
GROUP BY g.current_difficulty_level
ORDER BY avg_rounds_completed DESC;


-- 1C) Game duration by difficulty, file: analytics/game_duration_by_difficulty.sql
-- This shows how long players spend in games on average, broken down by difficulty
SELECT
  current_difficulty_level,
  COUNT(*) AS games,
  ROUND(AVG((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS avg_duration_seconds,
  ROUND(MIN((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS min_duration_seconds,
  ROUND(MAX((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS max_duration_seconds
FROM Games
WHERE started_at IS NOT NULL
  AND ended_at IS NOT NULL
GROUP BY current_difficulty_level
ORDER BY avg_duration_seconds ASC;


-- 1D) Game progress: How far do users get? (file: analytics/game_progress_distribution.sql)
SELECT
  CASE 
    WHEN total_rounds_completed = 0 THEN '0 rounds'
    WHEN total_rounds_completed BETWEEN 1 AND 3 THEN '1-3 rounds'
    WHEN total_rounds_completed BETWEEN 4 AND 6 THEN '4-6 rounds'
    WHEN total_rounds_completed BETWEEN 7 AND 12 THEN '7-12 rounds'
    WHEN total_rounds_completed BETWEEN 13 AND 17 THEN '13-17 rounds'
    WHEN total_rounds_completed = 18 THEN '18 rounds (complete)'
    ELSE 'other'
  END AS progress_bucket,
  COUNT(*) AS games,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM Games), 2) AS pct_of_games
FROM Games
GROUP BY progress_bucket
ORDER BY MIN(total_rounds_completed);


-- ============================================================================
-- 2) ROUND-LEVEL ANALYTICS (Individual word-guessing challenges)
-- ============================================================================

-- 2A) Round win rate by difficulty and category, file: analytics/round_win_rate_by_difficulty_category.sql
SELECT
  difficulty_level,
  category,
  COUNT(*) AS rounds,
  SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
  ROUND(100.0 * SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) / COUNT(*), 2) AS win_rate_pct
FROM Rounds
WHERE outcome IN ('win','loss','timeout','quit')
GROUP BY difficulty_level, category
ORDER BY win_rate_pct DESC, rounds DESC;


-- 2B) Round win rate by game mode, file: analytics/round_win_rate_by_game_mode.sql
SELECT
  game_mode,
  COUNT(*) AS rounds,
  SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
  SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
  ROUND(100.0 * SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) / COUNT(*), 2) AS win_rate_pct
FROM Rounds
WHERE outcome IN ('win','loss','timeout','quit')
GROUP BY game_mode
ORDER BY win_rate_pct DESC;


-- 2C) AI round win rate in ai_guesses mode, file: analytics/round_win_rate_ai_guesses.sql
SELECT
  category,
  difficulty_level,
  COUNT(*) AS rounds,
  SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS ai_correct_rounds,
  ROUND(100.0 * SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) / COUNT(*), 2) AS ai_round_win_rate_pct
FROM Rounds
WHERE game_mode = 'ai_guesses'
  AND outcome IN ('win','loss','timeout','quit')
GROUP BY category, difficulty_level
ORDER BY ai_round_win_rate_pct DESC, rounds DESC;


-- 2D) Average actions per round by mode (guesses/hints/descriptions)
SELECT
  r.game_mode,
  COUNT(DISTINCT r.round_id) AS rounds,
  ROUND(AVG(action_counts.total_actions), 2) AS avg_actions_per_round
FROM Rounds r
LEFT JOIN (
  SELECT round_id, COUNT(*) AS total_actions
  FROM Actions
  GROUP BY round_id
) action_counts ON action_counts.round_id = r.round_id
GROUP BY r.game_mode
ORDER BY rounds DESC;


-- ============================================================================
-- 3) GAME + ROUND COMBINED ANALYTICS
-- ============================================================================

-- 3A) Performance by round number (1-18): Which rounds are hardest? (file: analytics/performance_by_round_number.sql)
-- This analyzes how players perform on each round number within a game.
SELECT
  round_number,
  COUNT(*) AS rounds,
  SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
  ROUND(100.0 * SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) / COUNT(*), 2) AS win_rate_pct,
  ROUND(AVG((SELECT COUNT(*) FROM Actions a WHERE a.round_id = Rounds.round_id)), 2) AS avg_actions
FROM Rounds
WHERE round_number IS NOT NULL
  AND outcome IN ('win','loss','timeout','quit')
GROUP BY round_number
ORDER BY round_number;


-- 3B) User performance across games (file: analytics/user_performance_across_games.sql)
-- This aggregates user performance at the game level, showing how many games they've played, how many rounds they've completed, and their overall win rate. It helps identify power users and their success rates.
SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id) AS username,
  COUNT(DISTINCT g.game_id) AS total_games,
  SUM(CASE WHEN g.outcome = 'completed' THEN 1 ELSE 0 END) AS games_completed,
  COUNT(r.round_id) AS total_rounds,
  SUM(CASE WHEN r.outcome = 'win' THEN 1 ELSE 0 END) AS rounds_won,
  ROUND(100.0 * SUM(CASE WHEN r.outcome = 'win' THEN 1 ELSE 0 END) / NULLIF(COUNT(r.round_id), 0), 2) AS round_win_rate_pct
FROM Users u
LEFT JOIN Games g ON g.user_id = u.user_id
LEFT JOIN Rounds r ON r.game_id = g.game_id
GROUP BY u.user_id, username
ORDER BY round_win_rate_pct DESC, total_rounds DESC;


-- 3C) Game-level AI performance (file: analytics/game_level_ai_performance.sql)
SELECT
  g.game_id,
  g.current_difficulty_level,
  g.total_rounds_completed,
  COUNT(r.round_id) AS ai_rounds_in_game,
  SUM(CASE WHEN r.outcome = 'win' THEN 1 ELSE 0 END) AS ai_wins,
  ROUND(100.0 * SUM(CASE WHEN r.outcome = 'win' THEN 1 ELSE 0 END) / COUNT(r.round_id), 2) AS ai_win_rate_pct
FROM Games g
JOIN Rounds r ON r.game_id = g.game_id
WHERE r.game_mode = 'ai_guesses'
GROUP BY g.game_id, g.current_difficulty_level, g.total_rounds_completed
ORDER BY g.game_id DESC;


-- ============================================================================
-- 4) USER ANALYTICS
-- ============================================================================

-- 4A) Top users by total games played (file: analytics/top_users_by_games.sql)
SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id) AS username,
  COUNT(g.game_id) AS total_games,
  SUM(g.total_rounds_completed) AS total_rounds_played,
  MAX(g.started_at) AS last_game_started_at
FROM Users u
LEFT JOIN Games g ON g.user_id = u.user_id
GROUP BY u.user_id, username
ORDER BY total_games DESC, total_rounds_played DESC;


-- ============================================================================
-- 5) REFEREE / VIOLATIONS ANALYTICS
-- ============================================================================

-- 5A) Invalid attempts per round
SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id) AS username,
  r.round_id,
  r.secret_word,
  COUNT(rc.check_id) AS total_referee_checks,
  SUM(CASE WHEN rc.is_valid = 0 THEN 1 ELSE 0 END) AS invalid_attempts
FROM Users u
JOIN Games g ON g.user_id = u.user_id
JOIN Rounds r ON r.game_id = g.game_id
LEFT JOIN Referee_Checks rc ON rc.round_id = r.round_id
GROUP BY u.user_id, username, r.round_id, r.secret_word
ORDER BY invalid_attempts DESC, total_referee_checks DESC;


-- 5B) Invalid attempts per user overall
SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id) AS username,
  COUNT(rc.check_id) AS total_checks,
  SUM(CASE WHEN rc.is_valid = 0 THEN 1 ELSE 0 END) AS invalid_attempts,
  ROUND(
    100.0 * SUM(CASE WHEN rc.is_valid = 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(rc.check_id), 0),
    2
  ) AS invalid_rate_pct
FROM Users u
JOIN Games g ON g.user_id = u.user_id
JOIN Rounds r ON r.game_id = g.game_id
LEFT JOIN Referee_Checks rc ON rc.round_id = r.round_id
GROUP BY u.user_id, username
ORDER BY invalid_attempts DESC, invalid_rate_pct DESC;


-- 5C) Most common violation types (file: analytics/violation_types.sql)
SELECT
  violation_type,
  COUNT(*) AS occurrences,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM Referee_Checks WHERE is_valid = 0), 2) AS pct_of_violations
FROM Referee_Checks
WHERE is_valid = 0
  AND violation_type IS NOT NULL
GROUP BY violation_type
ORDER BY occurrences DESC;


-- ============================================================================
-- 6) TIME ANALYTICS
-- ============================================================================

-- 6A) Average time per user per action type
SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id) AS username,
  a.action_type,
  COUNT(*) AS n,
  ROUND(AVG(a.duration_ms) / 1000.0, 2) AS avg_s,
  ROUND(MIN(a.duration_ms) / 1000.0, 2) AS min_s,
  ROUND(MAX(a.duration_ms) / 1000.0, 2) AS max_s
FROM Users u
JOIN Games g ON g.user_id = u.user_id
JOIN Rounds r ON r.game_id = g.game_id
JOIN Actions a ON a.round_id = r.round_id
WHERE a.actor = 'user'
  AND a.duration_ms IS NOT NULL
GROUP BY u.user_id, username, a.action_type
ORDER BY avg_s ASC, n DESC;


-- 6B) Average round duration by outcome
SELECT
  outcome,
  COUNT(*) AS rounds,
  ROUND(AVG((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS avg_round_seconds,
  ROUND(MIN((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS min_round_seconds,
  ROUND(MAX((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS max_round_seconds
FROM Rounds
WHERE started_at IS NOT NULL
  AND ended_at IS NOT NULL
  AND outcome IN ('win','loss','timeout','quit')
GROUP BY outcome
ORDER BY avg_round_seconds ASC;


-- ============================================================================
-- 7) CATEGORY / DIFFICULTY ANALYTICS
-- ============================================================================

-- 7A) Most common categories picked
SELECT
  category,
  COUNT(*) AS rounds
FROM Rounds
GROUP BY category
ORDER BY rounds DESC;


-- 7B) Difficulty distribution across games, file: analytics/difficulty_distribution_accross_games.sql
SELECT
  current_difficulty_level,
  COUNT(*) AS games,
  SUM(total_rounds_completed) AS total_rounds
FROM Games
GROUP BY current_difficulty_level
ORDER BY games DESC;


-- 7C) Difficulty advancement tracking (file: analytics/difficulty_advancement.sql)
SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id) AS username,
  g.game_id,
  g.difficulty AS starting_difficulty,
  g.current_difficulty_level AS final_difficulty,
  g.difficulty_advancement_count AS times_advanced,
  g.total_rounds_completed
FROM Users u
JOIN Games g ON g.user_id = u.user_id
WHERE g.difficulty_advancement_count > 0
ORDER BY g.difficulty_advancement_count DESC, g.total_rounds_completed DESC;


-- ============================================================================
-- 8) QUICK QUITS
-- ============================================================================

-- 8A) Rounds that were quit quickly (very few actions) (file: analytics/quick_quits_rounds.sql)
SELECT
  r.round_id,
  COALESCE(u.username, u.participant_id) AS username,
  r.game_mode,
  r.outcome,
  COUNT(a.action_id) AS total_actions,
  r.started_at,
  r.ended_at
FROM Rounds r
JOIN Games g ON g.game_id = r.game_id
JOIN Users u ON u.user_id = g.user_id
LEFT JOIN Actions a ON a.round_id = r.round_id
WHERE r.outcome = 'quit'
GROUP BY r.round_id, username, r.game_mode, r.outcome, r.started_at, r.ended_at
HAVING COUNT(a.action_id) <= 3
ORDER BY r.ended_at DESC;


-- 8B) Games that were quit early (< 3 rounds completed) (file: analytics/early_game_quits.sql)
SELECT
  g.game_id,
  COALESCE(u.username, u.participant_id) AS username,
  g.current_difficulty_level,
  g.total_rounds_completed,
  g.outcome,
  g.started_at,
  g.ended_at
FROM Games g
JOIN Users u ON u.user_id = g.user_id
WHERE g.outcome = 'quit'
  AND g.total_rounds_completed < 3
ORDER BY g.ended_at DESC;


-- ============================================================================
-- 9) AI RESPONSE ANALYTICS (NEW!)
-- ============================================================================

-- 9A) AI response count by request type (file: analytics/ai_response_types.sql)
SELECT
  request_type,
  COUNT(*) AS responses,
  COUNT(DISTINCT round_id) AS unique_rounds
FROM AI_Responses
GROUP BY request_type
ORDER BY responses DESC;


-- 9B) AI model usage distribution (file: analytics/ai_model_usage.sql)
SELECT
  model,
  COUNT(*) AS responses,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM AI_Responses), 2) AS pct_of_responses
FROM AI_Responses
WHERE model IS NOT NULL
GROUP BY model
ORDER BY responses DESC;



-- ============================================================================
-- 10) GAME WIN RATE ANALYTICS (User vs AI)
-- ============================================================================
-- NOTE: game_mode values used here:
--   'user_guesses' = AI describes, user guesses (odd rounds: 1,3,5,...,17)
--   'ai_guesses'   = User describes, AI guesses (even rounds: 2,4,6,...,18)
-- The Games.winner column stores: 'user', 'ai', or 'tie'
-- ============================================================================


-- 10A) Overall game win rate: User vs AI vs Tie (file: analytics/game_win_rate_overall.sql)
-- How often does the user win, AI win, or tie across all completed games?
SELECT
  COUNT(*)                                                                         AS total_completed_games,
  SUM(CASE WHEN winner = 'user' THEN 1 ELSE 0 END)                                AS user_wins,
  SUM(CASE WHEN winner = 'ai'   THEN 1 ELSE 0 END)                                AS ai_wins,
  SUM(CASE WHEN winner = 'tie'  THEN 1 ELSE 0 END)                                AS ties,
  ROUND(100.0 * SUM(CASE WHEN winner = 'user' THEN 1 ELSE 0 END) / COUNT(*), 2)  AS user_win_rate_pct,
  ROUND(100.0 * SUM(CASE WHEN winner = 'ai'   THEN 1 ELSE 0 END) / COUNT(*), 2)  AS ai_win_rate_pct,
  ROUND(100.0 * SUM(CASE WHEN winner = 'tie'  THEN 1 ELSE 0 END) / COUNT(*), 2)  AS tie_rate_pct
FROM Games
WHERE outcome = 'completed'
  AND winner IS NOT NULL;


-- 10B) Game win rate per user (file: analytics/game_win_rate_per_user.sql)
-- How often does each individual user beat the AI?
SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id)                                           AS username,
  COUNT(g.game_id)                                                                 AS completed_games,
  SUM(CASE WHEN g.winner = 'user' THEN 1 ELSE 0 END)                              AS user_wins,
  SUM(CASE WHEN g.winner = 'ai'   THEN 1 ELSE 0 END)                              AS ai_wins,
  SUM(CASE WHEN g.winner = 'tie'  THEN 1 ELSE 0 END)                              AS ties,
  ROUND(100.0 * SUM(CASE WHEN g.winner = 'user' THEN 1 ELSE 0 END) / COUNT(g.game_id), 2) AS user_win_rate_pct
FROM Users u
JOIN Games g ON g.user_id = u.user_id
WHERE g.outcome = 'completed'
  AND g.winner IS NOT NULL
GROUP BY u.user_id, username
ORDER BY user_win_rate_pct DESC, completed_games DESC;


-- 10C) Game win rate by final difficulty reached (file: analytics/game_win_rate_by_difficulty.sql)
-- Does the user win more often at lower or higher difficulties?
SELECT
  g.current_difficulty_level                                                        AS final_difficulty,
  COUNT(g.game_id)                                                                  AS completed_games,
  SUM(CASE WHEN g.winner = 'user' THEN 1 ELSE 0 END)                               AS user_wins,
  SUM(CASE WHEN g.winner = 'ai'   THEN 1 ELSE 0 END)                               AS ai_wins,
  SUM(CASE WHEN g.winner = 'tie'  THEN 1 ELSE 0 END)                               AS ties,
  ROUND(100.0 * SUM(CASE WHEN g.winner = 'user' THEN 1 ELSE 0 END) / COUNT(g.game_id), 2) AS user_win_rate_pct,
  ROUND(100.0 * SUM(CASE WHEN g.winner = 'ai'   THEN 1 ELSE 0 END) / COUNT(g.game_id), 2) AS ai_win_rate_pct
FROM Games g
WHERE g.outcome = 'completed'
  AND g.winner IS NOT NULL
GROUP BY g.current_difficulty_level
ORDER BY
  CASE g.current_difficulty_level
    WHEN 'easy1' THEN 1 WHEN 'easy2' THEN 2 WHEN 'easy3' THEN 3
    WHEN 'medium1' THEN 4 WHEN 'medium2' THEN 5 WHEN 'medium3' THEN 6
    WHEN 'hard1' THEN 7 WHEN 'hard2' THEN 8 WHEN 'hard3' THEN 9
    ELSE 10
  END;


-- 10D) Average final time left by winner (file: analytics/avg_final_time_by_winner.sql)
-- How much time does the winning side typically have left?
-- This reveals how close games typically are.
SELECT
  winner,
  COUNT(*)                                                   AS games,
  ROUND(AVG(user_final_time), 1)                             AS avg_user_time_left_s,
  ROUND(AVG(ai_final_time), 1)                               AS avg_ai_time_left_s,
  ROUND(AVG(ABS(user_final_time - ai_final_time)), 1)        AS avg_time_margin_s,
  ROUND(MIN(ABS(user_final_time - ai_final_time)), 1)        AS closest_game_margin_s,
  ROUND(MAX(ABS(user_final_time - ai_final_time)), 1)        AS biggest_margin_s
FROM Games
WHERE outcome = 'completed'
  AND winner IS NOT NULL
  AND user_final_time IS NOT NULL
  AND ai_final_time IS NOT NULL
GROUP BY winner
ORDER BY FIELD(winner, 'user', 'ai', 'tie');


-- ============================================================================
-- END OF FILE
-- ============================================================================
