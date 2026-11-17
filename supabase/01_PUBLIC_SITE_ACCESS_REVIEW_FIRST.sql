-- REVIEW BEFORE RUNNING. Backup your database first.
-- Goal: expose only public listing columns; allow submitted inquiries/reviews
-- without exposing other guests' inquiries or unapproved reviews.
-- IMPORTANT: This script removes and replaces existing policies for THESE THREE TABLES.
-- If other systems use them, review 00_PRECHECK_READ_ONLY.sql first.
BEGIN;

-- Properties: all internal rates, commission_rate and any additional columns remain inaccessible
-- to anon/authenticated Data API roles. PostgREST must not receive a table-level SELECT grant.
ALTER TABLE public.properties ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.properties FROM PUBLIC, anon, authenticated;
GRANT SELECT (id,title,location,unit_type,description,image_url,created_at,is_active,is_featured,beds,folder_path)
 ON public.properties TO anon, authenticated;
DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT policyname FROM pg_policies WHERE schemaname='public' AND tablename='properties' LOOP
  EXECUTE format('DROP POLICY %I ON public.properties',r.policyname);
 END LOOP;
END $$;
CREATE POLICY properties_public_active_read ON public.properties
 FOR SELECT TO anon, authenticated USING (is_active IS TRUE);

-- Guest inquiries: write-only for browser visitors. No SELECT/UPDATE/DELETE permissions.
ALTER TABLE public.inquiries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.inquiries FROM PUBLIC, anon, authenticated;
GRANT INSERT (name,email,phone,country,service,message) ON public.inquiries TO anon, authenticated;
GRANT USAGE ON SEQUENCE public.inquiries_id_seq TO anon, authenticated;
DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT policyname FROM pg_policies WHERE schemaname='public' AND tablename='inquiries' LOOP
  EXECUTE format('DROP POLICY %I ON public.inquiries',r.policyname);
 END LOOP;
END $$;
CREATE POLICY inquiries_public_submit ON public.inquiries
 FOR INSERT TO anon, authenticated WITH CHECK (
  char_length(coalesce(name,'')) BETWEEN 1 AND 150
  AND char_length(coalesce(message,'')) BETWEEN 5 AND 5000
  AND char_length(coalesce(email,'')) BETWEEN 3 AND 320
 );

-- Reviews: visitor can submit review for approval, not publish their own approval.
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.reviews FROM PUBLIC, anon, authenticated;
GRANT SELECT (id,name,city,country,rating,comment,approved,created_at) ON public.reviews TO anon, authenticated;
GRANT INSERT (name,city,country,rating,comment,approved) ON public.reviews TO anon, authenticated;
GRANT USAGE ON SEQUENCE public.reviews_id_seq TO anon, authenticated;
DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT policyname FROM pg_policies WHERE schemaname='public' AND tablename='reviews' LOOP
  EXECUTE format('DROP POLICY %I ON public.reviews',r.policyname);
 END LOOP;
END $$;
CREATE POLICY reviews_public_approved_read ON public.reviews
 FOR SELECT TO anon, authenticated USING (approved IS TRUE);
CREATE POLICY reviews_public_unapproved_submit ON public.reviews
 FOR INSERT TO anon, authenticated WITH CHECK (
  approved IS FALSE AND rating BETWEEN 1 AND 5
  AND char_length(coalesce(name,'')) BETWEEN 1 AND 100
  AND char_length(coalesce(comment,'')) BETWEEN 3 AND 2000
 );
COMMIT;

-- After running:
-- 1) Verify anonymous visitors can READ active public property fields, not 'price' or 'commission_rate'.
-- 2) Verify anonymous users CANNOT READ inquiries, bookings or unapproved reviews.
-- 3) Verify review/inquiry forms work; review moderation remains in Supabase dashboard.
-- 4) Do not assume this secures bookings. See 02_ADMIN_BOOKINGS... SQL.
-- 5) Anonymous submissions can be spammed; consider a server-side CAPTCHA/rate limit later.
