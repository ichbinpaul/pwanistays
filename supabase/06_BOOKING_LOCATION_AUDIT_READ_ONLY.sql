-- PwaniStays booking location audit. Paste into the project's Supabase SQL Editor.
-- Read-only. Returns booking IDs, unit labels, statuses, locations and contribution.
-- Run across all dates to compare with the former dashboard screenshots.
WITH source AS (
    SELECT id::text AS booking_id,
           COALESCE(trim(regexp_replace(unit_name::text, '[[:space:]]+', ' ', 'g')), '') AS unit,
           COALESCE(trim(regexp_replace(location::text, '[[:space:]]+', ' ', 'g')), '') AS recorded_location,
           COALESCE(NULLIF(trim(status::text), ''), 'Unspecified') AS status,
           trim(guest_paid::text) AS paid_text,
           trim(host_cost::text) AS host_text,
           trim(charges::text) AS charges_text
    FROM public.bookings
), prepared AS (
    SELECT *,
           trim(regexp_replace(lower(unit), '[[:space:],–—-]+', ' ', 'g')) AS name_key,
           lower(recorded_location) AS location_key,
           lower(status) AS status_key,
           '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' AS number_pattern
    FROM source
), recognized AS (
    SELECT *,
           CASE
               WHEN name_key ~ '^coral sands( ((residen|reciden)ce|apartment)(s|[(]s[)])?)?( (nyali|diani))?$' THEN 'coral sands residences'
               WHEN name_key ~ '^mwembe tayari( ?(nyali|mombasa( town)?))?$' THEN 'mwembe tayari'
           END AS confirmed_unit
    FROM prepared
), classified AS (
    SELECT *,
           COALESCE(confirmed_unit, CASE
               WHEN lower(unit) IN ('aqua garden', 'aqua gardens') THEN 'aqua garden'
               WHEN lower(unit) IN ('bxton point', 'buxton point') THEN 'buxton point'
               WHEN lower(unit) IN ('coral gables apart', 'coral gables apartment(s)') THEN 'coral gables'
               ELSE regexp_replace(lower(unit), ' apartments?$', '')
           END) AS unit_key,
           CASE WHEN paid_text ~ number_pattern THEN paid_text::numeric END AS paid,
           CASE WHEN host_text ~ number_pattern THEN host_text::numeric END AS host_cost,
           CASE WHEN charges_text ~ number_pattern THEN charges_text::numeric END AS charges
    FROM recognized
), locations AS (
    SELECT *,
           CASE confirmed_unit
               WHEN 'coral sands residences' THEN 'Nyali'
               WHEN 'mwembe tayari' THEN 'Mombasa'
           END AS confirmed_location,
           COALESCE(paid, 0) - COALESCE(host_cost, 0) - COALESCE(charges, 0) AS former_contribution,
           CASE WHEN paid IS NOT NULL
                     AND (host_cost IS NOT NULL OR NULLIF(host_text, '') IS NULL)
                     AND (charges IS NOT NULL OR NULLIF(charges_text, '') IS NULL)
                THEN round(paid - COALESCE(host_cost, 0) - COALESCE(charges, 0), 2)
           END AS current_contribution
    FROM classified
), counts AS (
    SELECT unit_key, location_key, min(recorded_location) AS label, count(*) AS bookings
    FROM locations
    WHERE unit_key <> '' AND location_key <> ''
    GROUP BY unit_key, location_key
), ranked AS (
    SELECT *, dense_rank() OVER (PARTITION BY unit_key ORDER BY bookings DESC) AS frequency_rank
    FROM counts
), patterns AS (
    SELECT unit_key, count(*) AS recorded_locations,
           min(label) FILTER (WHERE frequency_rank = 1) AS most_frequent,
           count(*) FILTER (WHERE frequency_rank = 1) AS tie_count,
           string_agg(label || ' (' || bookings || ')', ', ' ORDER BY bookings DESC, label) AS frequency
    FROM ranked
    GROUP BY unit_key
), details AS (
    SELECT l.*, p.frequency,
           COALESCE(l.confirmed_location, NULLIF(l.recorded_location, ''), '(blank)') AS report_location,
           CASE WHEN p.tie_count = 1 THEN p.most_frequent END AS usual_location,
           CASE
               WHEN l.confirmed_location IS NOT NULL AND l.location_key <> lower(l.confirmed_location) THEN 'Conflicts with confirmed location'
               WHEN l.location_key = '' THEN 'Booking has no recorded location'
               WHEN l.confirmed_location IS NULL AND p.recorded_locations > 1 AND p.tie_count > 1 THEN 'Location conflict with a tie; review the unit'
               WHEN l.confirmed_location IS NULL AND p.recorded_locations > 1
                    AND l.location_key <> lower(p.most_frequent) THEN 'Unit recorded more often in another location; confirm before editing'
           END AS reason
    FROM locations l
    LEFT JOIN patterns p USING (unit_key)
), output AS (
    SELECT '01 Booking to review' AS section, booking_id, unit, status,
           COALESCE(NULLIF(recorded_location, ''), '(blank)') AS recorded_location,
           COALESCE(confirmed_location, usual_location) AS location_to_check,
           frequency AS recorded_counts, reason AS detail,
           1::bigint AS bookings, former_contribution AS contribution_kes
    FROM details
    WHERE reason IS NOT NULL
    UNION ALL
    SELECT '02 Recorded location, all statuses', NULL, NULL, NULL,
           COALESCE(NULLIF(min(recorded_location), ''), '(blank)'), NULL, NULL,
           'Former calculation using the recorded location', count(*), sum(former_contribution)
    FROM details
    GROUP BY location_key
    UNION ALL
    SELECT '03 Report location, all statuses', NULL, NULL, NULL,
           NULL, min(report_location), NULL, 'All statuses after confirmed location corrections', count(*), sum(former_contribution)
    FROM details
    GROUP BY lower(report_location)
    UNION ALL
    SELECT '04 Report location, completed', NULL, NULL, 'Complete',
           NULL, min(report_location), NULL, 'Completed-stay dashboard calculation', count(*), sum(current_contribution)
    FROM details
    WHERE status_key = 'complete'
    GROUP BY lower(report_location)
    UNION ALL
    SELECT '05 Report location, excluded statuses', NULL, NULL, min(status),
           NULL, min(report_location), NULL, 'Contribution excluded from the completed-stay report', count(*), sum(former_contribution)
    FROM details
    WHERE status_key <> 'complete'
    GROUP BY lower(report_location), status_key
)
SELECT * FROM output
ORDER BY section, COALESCE(location_to_check, recorded_location), unit, booking_id, status;
