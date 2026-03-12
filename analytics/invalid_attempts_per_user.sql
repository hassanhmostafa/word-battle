-- 5B) Invalid attempts per user overall. file: analytics/invalid_attempts_per_user.sql
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