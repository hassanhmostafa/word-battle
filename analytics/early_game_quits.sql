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