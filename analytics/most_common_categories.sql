-- 7A) Most common categories picked (overall). file: analytics/most_common_categories.sql
SELECT
  category,
  COUNT(*) AS rounds
FROM Rounds
GROUP BY category
ORDER BY rounds DESC;