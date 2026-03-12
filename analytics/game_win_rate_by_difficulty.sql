-- 10C) Game win rate by final difficulty reached (file: analytics/game_win_rate_by_difficulty.sql)
-- Does the user win more often at lower or higher difficulties?
SELECT
  g.current_difficulty_level                                                        AS final_difficulty,
  COUNT(g.game_id)                                                                  AS completed_games,
  SUM(CASE WHEN g.winner = 'user' THEN 1 ELSE 0 END)                               AS user_wins,
  SUM(CASE WHEN g.winner = 'ai'   THEN 1 ELSE 0 END)                               AS ai_wins,
  SUM(CASE WHEN g.winner = 'tie'  THEN 1 ELSE 0 END)                               AS ties,
  ROUND(100.0 * SUM(CASE WHEN g.winner = 'user' THEN 1 ELSE 0 END) / COUNT(g.game_id), 2) AS user_win_rate_pct,
  ROUND(100.0 * SUM(CASE WHEN g.winner = 'ai'   THEN 1 ELSE 0 END) / COUNT(g.game_id), 2) AS ai_win_rate_pct
FROM Games g
WHERE g.outcome = 'completed'
  AND g.winner IS NOT NULL
GROUP BY g.current_difficulty_level
ORDER BY
  CASE g.current_difficulty_level
    WHEN 'easy1' THEN 1 WHEN 'easy2' THEN 2 WHEN 'easy3' THEN 3
    WHEN 'medium1' THEN 4 WHEN 'medium2' THEN 5 WHEN 'medium3' THEN 6
    WHEN 'hard1' THEN 7 WHEN 'hard2' THEN 8 WHEN 'hard3' THEN 9
    ELSE 10
  END;
