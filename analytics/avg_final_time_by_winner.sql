-- 10D) Average final time left by winner (file: analytics/avg_final_time_by_winner.sql)
-- How much time does the winning side typically have left?
-- This reveals how close games typically are.
SELECT
  winner,
  COUNT(*)                                                   AS games,
  ROUND(AVG(user_final_time), 1)                             AS avg_user_time_left_s,
  ROUND(AVG(ai_final_time), 1)                               AS avg_ai_time_left_s,
  ROUND(AVG(ABS(user_final_time - ai_final_time)), 1)        AS avg_time_margin_s,
  ROUND(MIN(ABS(user_final_time - ai_final_time)), 1)        AS closest_game_margin_s,
  ROUND(MAX(ABS(user_final_time - ai_final_time)), 1)        AS biggest_margin_s
FROM Games
WHERE outcome = 'completed'
  AND winner IS NOT NULL
  AND user_final_time IS NOT NULL
  AND ai_final_time IS NOT NULL
GROUP BY winner
ORDER BY FIELD(winner, 'user', 'ai', 'tie');