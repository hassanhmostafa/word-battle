-- 1A) Outcome counts per user (how many wins/losses/timeouts/quits/missing per user) file: analytics/outcome_counts_per_user.sql 
SELECT
  u.user_id,
  u.participant_id,
  COALESCE(u.username, u.participant_id) AS username,
  COUNT(g.game_id) AS total_games,
  SUM(CASE WHEN g.outcome = 'win' THEN 1 ELSE 0 END) AS wins,
  SUM(CASE WHEN g.outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
  SUM(CASE WHEN g.outcome = 'timeout' THEN 1 ELSE 0 END) AS timeouts,
  SUM(CASE WHEN g.outcome = 'quit' THEN 1 ELSE 0 END) AS quits,
  SUM(CASE WHEN g.outcome IS NULL THEN 1 ELSE 0 END) AS missing_outcome
FROM Users u
LEFT JOIN Games g ON g.user_id = u.user_id
GROUP BY u.user_id, u.participant_id, u.username
ORDER BY wins DESC, losses ASC, total_games DESC;