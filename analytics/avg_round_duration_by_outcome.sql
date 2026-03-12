-- 6B) Average round duration by outcome (uses started_at / ended_at) file: analytics/avg_round_duration_by_outcome.sql
SELECT
  outcome,
  COUNT(*) AS rounds,
  ROUND(AVG((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS avg_round_seconds,
  ROUND(MIN((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS min_round_seconds,
  ROUND(MAX((julianday(ended_at) - julianday(started_at)) * 86400.0), 2) AS max_round_seconds
FROM Rounds
WHERE started_at IS NOT NULL
  AND ended_at IS NOT NULL
  AND outcome IN ('win','loss','timeout','quit')
GROUP BY outcome
ORDER BY avg_round_seconds ASC;