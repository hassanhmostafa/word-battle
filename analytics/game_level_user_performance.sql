-- 3B) Game-level user performance (file: analytics/game_level_user_performance.sql)
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