-- PWANISTAYS AUTOMATIC FEATURED PROPERTY ROTATION — ONE-TIME SETUP
-- REVIEW and RUN ONCE in the Supabase SQL Editor of the CORRECT PwaniStays project.
-- This is NOT activated by putting this file in GitHub.
--
-- SCHEDULE: Daily 03:00 UTC = 06:00 Kenya time (EAT).
-- USE: 6 active properties featured at a time; fair deterministic round-robin.
-- SOURCE: public.properties (id uuid, is_active boolean, is_featured boolean).
-- IMPORTANT: This REPLACES manually selected is_featured flags daily.
-- NO property rows are deleted, IDs are preserved, and bookings/photos aren't edited.
-- Run 04_FEATURED_ROTATION_PREVIEW_READ_ONLY.sql BEFORE installing.
-- Must be run as the Supabase SQL Editor's privileged database role.
-- View executions in Supabase Dashboard > Integrations > Cron.
-- To stop: SELECT cron.unschedule('pwanistays-featured-daily');
--
-- Notes:
-- * We deliberately avoid any public REST API endpoint or service-role key.
-- * It changes only is_featured, and only where the value needs changing.
-- * A single database transaction updates the daily selection atomically.
-- * Adding/removing properties adjusts the round-robin automatically.
-- * If no properties are active, no properties remain featured.

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE SCHEMA IF NOT EXISTS pwani_internal;

CREATE OR REPLACE FUNCTION pwani_internal.rotate_featured_properties()
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $rotation$
DECLARE
  active_total integer;
  start_position integer;
  featured_total integer;
BEGIN
  -- Prevent two simultaneous invocations of this specific rotation job.
  PERFORM pg_catalog.pg_advisory_xact_lock(2026111706::bigint);

  SELECT count(*)::integer INTO active_total
  FROM public.properties
  WHERE is_active IS TRUE;

  IF active_total = 0 THEN
    UPDATE public.properties
    SET is_featured = FALSE
    WHERE is_featured IS DISTINCT FROM FALSE;
    RETURN 0;
  END IF;

  -- Every Kenya calendar day, advance by six unique property slots.
  -- Stable hashed UUID order prevents clustering by import date.
  start_position :=
     ((((now() AT TIME ZONE 'Africa/Nairobi')::date
         - DATE '2026-11-17') * 6) % active_total);

  WITH ordered AS (
    SELECT id,
      (row_number() OVER (ORDER BY md5(id::text), id) - 1)::integer AS position
    FROM public.properties
    WHERE is_active IS TRUE
  ), selected AS (
    SELECT id FROM ordered
    WHERE ((position - start_position + active_total) % active_total) < 6
  ), desired AS (
    SELECT p.id,
      (p.is_active IS TRUE AND s.id IS NOT NULL) AS next_featured
    FROM public.properties p
    LEFT JOIN selected s ON s.id = p.id
  )
  UPDATE public.properties p
  SET is_featured = d.next_featured
  FROM desired d
  WHERE p.id = d.id
    AND p.is_featured IS DISTINCT FROM d.next_featured;

  SELECT count(*)::integer INTO featured_total
  FROM public.properties
  WHERE is_active IS TRUE AND is_featured IS TRUE;

  RETURN featured_total;
END;
$rotation$;

-- Do not allow public/anonymous API callers to invoke the job manually.
REVOKE ALL ON FUNCTION pwani_internal.rotate_featured_properties() FROM PUBLIC;

-- pg_cron schedules in UTC/GMT by default on Supabase.
-- Calling cron.schedule again with this exact name updates that job rather than duplicating it.
SELECT cron.schedule(
  'pwanistays-featured-daily',
  '0 3 * * *',
  'SELECT pwani_internal.rotate_featured_properties();'
);

-- Verify setup (read only):
SELECT jobid, jobname, schedule, command, active
FROM cron.job
WHERE jobname = 'pwanistays-featured-daily';

-- OPTIONAL MANUAL FIRST ROTATION, if you want to apply today's group immediately:
-- SELECT pwani_internal.rotate_featured_properties();
--
-- OPTIONAL STOP:
-- SELECT cron.unschedule('pwanistays-featured-daily');
--
-- OPTIONAL RECENT RUN HISTORY (after first scheduled execution):
-- SELECT start_time, end_time, status, return_message
-- FROM cron.job_run_details
-- WHERE jobid = (SELECT jobid FROM cron.job WHERE jobname = 'pwanistays-featured-daily')
-- ORDER BY start_time DESC LIMIT 10;
