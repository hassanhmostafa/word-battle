-- 4B) Average guesses/hints per game by mode. file: analytics/avg_guesses_hints_per_game_mode.sql
SELECT
  game_mode,
  COUNT(*) AS games,
  ROUND(AVG(total_guesses), 2) AS avg_guesses,
  ROUND(AVG(total_hints), 2) AS avg_hints
FROM Games
GROUP BY game_mode
ORDER BY games DESC;