-- 2A) Round win rate by difficulty and category, file: analytics/round_win_rate_by_difficulty_category.sql
SELECT
  difficulty_level,
  category,
  COUNT(*) AS rounds,
  SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
  ROUND(100.0 * SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) / COUNT(*), 2) AS win_rate_pct
FROM Rounds
WHERE outcome IN ('win','loss','timeout','quit')
GROUP BY difficulty_level, category
ORDER BY win_rate_pct DESC, rounds DESC;