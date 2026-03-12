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