-- 2B) Round win rate by game mode, file: analytics/round_win_rate_by_game_mode.sql
SELECT
  game_mode,
  COUNT(*) AS rounds,
  SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
  SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
  ROUND(100.0 * SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) / COUNT(*), 2) AS win_rate_pct
FROM Rounds
WHERE outcome IN ('win','loss','timeout','quit')
GROUP BY game_mode
ORDER BY win_rate_pct DESC;