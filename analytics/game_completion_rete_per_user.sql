-- 1A) Game completion rate per user, file: analytics/game_completion_rete_per_user.sql
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