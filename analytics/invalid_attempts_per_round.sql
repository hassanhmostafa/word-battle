-- 5A) Invalid attempts per round file: analytics/invalid_attempts_per_round.sql
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