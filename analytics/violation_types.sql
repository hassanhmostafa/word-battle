-- 5C) Most common violation types (file: analytics/violation_types.sql)
SELECT
  violation_type,
  COUNT(*) AS occurrences,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM Referee_Checks WHERE is_valid = 0), 2) AS pct_of_violations
FROM Referee_Checks
WHERE is_valid = 0
  AND violation_type IS NOT NULL
GROUP BY violation_type
ORDER BY occurrences DESC;