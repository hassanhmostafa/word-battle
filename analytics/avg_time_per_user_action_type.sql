-- 6A) Average time per user per action type (guess vs description vs hint) file: analytics/avg_time_per_user_action_type.sql
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