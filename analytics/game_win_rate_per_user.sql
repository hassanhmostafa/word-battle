-- 10B) Game win rate per user (file: analytics/game_win_rate_per_user.sql)
-- How often does each individual user beat the AI?
SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id)                                           AS username,
  COUNT(g.game_id)                                                                 AS completed_games,
  SUM(CASE WHEN g.winner = 'user' THEN 1 ELSE 0 END)                              AS user_wins,
  SUM(CASE WHEN g.winner = 'ai'   THEN 1 ELSE 0 END)                              AS ai_wins,
  SUM(CASE WHEN g.winner = 'tie'  THEN 1 ELSE 0 END)                              AS ties,
  ROUND(100.0 * SUM(CASE WHEN g.winner = 'user' THEN 1 ELSE 0 END) / COUNT(g.game_id), 2) AS user_win_rate_pct
FROM Users u
JOIN Games g ON g.user_id = u.user_id
WHERE g.outcome = 'completed'
  AND g.winner IS NOT NULL
GROUP BY u.user_id, username
ORDER BY user_win_rate_pct DESC, completed_games DESC;