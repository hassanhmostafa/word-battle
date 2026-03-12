-- 2C) AI round win rate in ai_guesses mode, file: analytics/round_win_rate_ai_guesses.sql
SELECT
  category,
  difficulty_level,
  COUNT(*) AS rounds,
  SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS ai_correct_rounds,
  ROUND(100.0 * SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) / COUNT(*), 2) AS ai_round_win_rate_pct
FROM Rounds
WHERE game_mode = 'ai_guesses'
  AND outcome IN ('win','loss','timeout','quit')
GROUP BY category, difficulty_level
ORDER BY ai_round_win_rate_pct DESC, rounds DESC;