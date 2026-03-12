-- 4E) Top users by total games played (engagement). file: analytics/top_users_by_total_games.sql
SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id) AS username,
  COUNT(g.game_id) AS total_games,
  MAX(g.started_at) AS last_game_started_at
FROM Users u
LEFT JOIN Games g ON g.user_id = u.user_id
GROUP BY u.user_id, username
ORDER BY total_games DESC, last_game_started_at DESC;