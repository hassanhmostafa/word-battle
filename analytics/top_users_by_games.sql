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