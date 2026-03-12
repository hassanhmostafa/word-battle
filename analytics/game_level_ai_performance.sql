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