-- OPTIONAL BUT STRONGLY RECOMMENDED. THIS FILE WILL ABORT UNTIL YOU CONFIGURE YOUR ADMIN AUTH UID.
-- Backup bookings, review 00_PRECHECK_READ_ONLY.sql and authenticate once in Supabase Auth dashboard.
-- Copy the UUID from Authentication -> Users and replace the placeholder below.
-- ONLY authenticated users listed in site_admins will access the private bookings table.
-- WARNING: Existing bookings RLS policies are replaced; other users/apps will lose access.
BEGIN;

CREATE TABLE IF NOT EXISTS public.site_admins (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.site_admins ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.site_admins FROM PUBLIC, anon, authenticated;

DO $$
DECLARE admin_uid text := 'REPLACE-WITH-YOUR-SUPABASE-AUTH-USER-UUID';
BEGIN
  IF admin_uid = 'REPLACE-WITH-YOUR-SUPABASE-AUTH-USER-UUID' THEN
    RAISE EXCEPTION 'STOP: configure your admin user UUID before running this script.';
  END IF;
  INSERT INTO public.site_admins(user_id) VALUES (admin_uid::uuid) ON CONFLICT DO NOTHING;
END $$;

CREATE OR REPLACE FUNCTION public.is_pwanistays_admin()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT EXISTS (SELECT 1 FROM public.site_admins a WHERE a.user_id = (SELECT auth.uid()));
$$;
REVOKE ALL ON FUNCTION public.is_pwanistays_admin() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_pwanistays_admin() TO authenticated;

ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.bookings FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.bookings TO authenticated;
DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT policyname FROM pg_policies WHERE schemaname='public' AND tablename='bookings' LOOP
  EXECUTE format('DROP POLICY %I ON public.bookings',r.policyname);
 END LOOP;
END $$;
CREATE POLICY bookings_admin_select ON public.bookings FOR SELECT TO authenticated USING ((select public.is_pwanistays_admin()));
CREATE POLICY bookings_admin_insert ON public.bookings FOR INSERT TO authenticated WITH CHECK ((select public.is_pwanistays_admin()));
CREATE POLICY bookings_admin_update ON public.bookings FOR UPDATE TO authenticated USING ((select public.is_pwanistays_admin())) WITH CHECK ((select public.is_pwanistays_admin()));
CREATE POLICY bookings_admin_delete ON public.bookings FOR DELETE TO authenticated USING ((select public.is_pwanistays_admin()));
COMMIT;
-- Test with your admin login and an ordinary/non-admin account before considering complete.
-- Supabase SQL Editor database owner can still manage records independently of RLS.
