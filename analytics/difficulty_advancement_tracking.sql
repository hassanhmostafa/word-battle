SELECT
  u.user_id,
  COALESCE(u.username, u.participant_id) AS username,
  g.game_id,
  g.difficulty AS starting_difficulty,
  g.current_difficulty_level AS final_difficulty,
  g.difficulty_advancement_count AS times_advanced,
  g.total_rounds_completed
FROM Users u
JOIN Games g ON g.user_id = u.user_id
WHERE g.difficulty_advancement_count > 0
ORDER BY g.difficulty_advancement_count DESC, g.total_rounds_completed DESC;