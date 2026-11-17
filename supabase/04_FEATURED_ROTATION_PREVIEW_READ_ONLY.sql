-- PWANISTAYS FEATURED ROTATION — READ ONLY PREVIEW
-- Safe to run in Supabase SQL Editor. Does not modify any property records.
-- Matches the proposed daily six-property rotation using Kenya calendar dates.
-- For about 132 active properties, each property will be selected once in a
-- 22-day cycle, with variations if active inventory changes.

SELECT
  count(*) FILTER (WHERE is_active IS TRUE) AS active_properties,
  count(*) FILTER (WHERE is_active IS TRUE AND is_featured IS TRUE) AS currently_featured,
  LEAST(6, count(*) FILTER (WHERE is_active IS TRUE)) AS proposed_daily_featured
FROM public.properties;

WITH eligible AS (
  SELECT
    id,
    title,
    location,
    is_featured,
    (row_number() OVER (ORDER BY md5(id::text), id) - 1)::integer AS position
  FROM public.properties
  WHERE is_active IS TRUE
), totals AS (
  SELECT count(*)::integer AS n FROM eligible
), offset_for_today AS (
  SELECT
    n,
    ((((now() AT TIME ZONE 'Africa/Nairobi')::date - DATE '2026-11-17') * 6) % NULLIF(n, 0)) AS offset
  FROM totals
)
SELECT e.position, e.id, e.title, e.location,
       e.is_featured AS currently_featured
FROM eligible e
CROSS JOIN offset_for_today d
WHERE d.n > 0
  AND ((e.position - d.offset + d.n) % d.n) < 6
ORDER BY ((e.position - d.offset + d.n) % d.n), e.position;
