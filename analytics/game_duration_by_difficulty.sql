-- 1C) Game duration by difficulty, file: analytics/game_duration_by_difficulty.sql
-- This shows how long players spend in games on average, broken down by difficulty
SELECT
  current_difficulty_level,
  COUNT(*) AS games,
  ROUND(AVG((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS avg_duration_seconds,
  ROUND(MIN((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS min_duration_seconds,
  ROUND(MAX((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS max_duration_seconds
FROM Games
WHERE started_at IS NOT NULL
  AND ended_at IS NOT NULL
GROUP BY current_difficulty_level
ORDER BY avg_duration_seconds ASC;