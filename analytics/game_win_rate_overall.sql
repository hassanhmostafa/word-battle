-- 10A) Overall game win rate: User vs AI vs Tie (file: analytics/game_win_rate_overall.sql)
-- How often does the user win, AI win, or tie across all completed games?
SELECT
  COUNT(*)                                                                         AS total_completed_games,
  SUM(CASE WHEN winner = 'user' THEN 1 ELSE 0 END)                                AS user_wins,
  SUM(CASE WHEN winner = 'ai'   THEN 1 ELSE 0 END)                                AS ai_wins,
  SUM(CASE WHEN winner = 'tie'  THEN 1 ELSE 0 END)                                AS ties,
  ROUND(100.0 * SUM(CASE WHEN winner = 'user' THEN 1 ELSE 0 END) / COUNT(*), 2)  AS user_win_rate_pct,
  ROUND(100.0 * SUM(CASE WHEN winner = 'ai'   THEN 1 ELSE 0 END) / COUNT(*), 2)  AS ai_win_rate_pct,
  ROUND(100.0 * SUM(CASE WHEN winner = 'tie'  THEN 1 ELSE 0 END) / COUNT(*), 2)  AS tie_rate_pct
FROM Games
WHERE outcome = 'completed'
  AND winner IS NOT NULL;