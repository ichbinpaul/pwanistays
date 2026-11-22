-- Run the read-only preflight first. Review any views, routines or integrations
-- that expose or depend on bookings. Back up the current grants and policies.
-- Replace the placeholder below with your Authentication → Users UUID.
-- List any other explicitly approved staff UUIDs, separated by commas.
BEGIN;

SET LOCAL pwanistays.booking_admins = 'REPLACE-WITH-YOUR-SUPABASE-AUTH-USER-UUID';

DO $$
DECLARE
    configured_ids text := current_setting('pwanistays.booking_admins');
    approved_ids uuid[];
BEGIN
    IF configured_ids = '' OR configured_ids LIKE '%REPLACE-%' THEN
        RAISE EXCEPTION 'Set at least one approved Supabase Auth user UUID before running this migration.';
    END IF;
    SELECT array_agg(DISTINCT trim(id)::uuid)
    INTO approved_ids
    FROM unnest(string_to_array(configured_ids, ',')) AS ids(id);

    IF EXISTS (
        SELECT 1 FROM unnest(approved_ids) AS approved(user_id)
        WHERE NOT EXISTS (SELECT 1 FROM auth.users u WHERE u.id = approved.user_id)
    ) THEN
        RAISE EXCEPTION 'Every approved UUID must match a user in this Supabase project.';
    END IF;

    CREATE TABLE IF NOT EXISTS public.site_admins (
        user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    LOCK TABLE public.site_admins IN SHARE ROW EXCLUSIVE MODE;

    IF EXISTS (SELECT 1 FROM public.site_admins WHERE user_id <> ALL (approved_ids)) THEN
        RAISE EXCEPTION 'Existing site_admins includes a user outside your approved list. Review the existing membership before proceeding.';
    END IF;
    INSERT INTO public.site_admins (user_id)
    SELECT unnest(approved_ids) ON CONFLICT DO NOTHING;
END $$;

ALTER TABLE public.site_admins ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.site_admins, public.bookings FROM PUBLIC, anon, authenticated;

-- Table-level revokes do not remove separately granted column permissions.
DO $$
DECLARE
    target_table text;
    columns text;
BEGIN
    FOREACH target_table IN ARRAY ARRAY['site_admins', 'bookings'] LOOP
        SELECT string_agg(quote_ident(attname), ', ')
        INTO columns
        FROM pg_attribute
        WHERE attrelid = to_regclass(format('public.%I', target_table)) AND attnum > 0 AND NOT attisdropped;
        EXECUTE format(
            'REVOKE ALL PRIVILEGES (%s) ON TABLE public.%I FROM PUBLIC, anon, authenticated',
            columns, target_table
        );
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION public.is_pwanistays_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.site_admins a WHERE a.user_id = (SELECT auth.uid())
    );
$$;
REVOKE ALL ON FUNCTION public.is_pwanistays_admin() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.is_pwanistays_admin() TO authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.bookings TO authenticated;

-- Keep existing policies. The restrictive gate is required even if there is
-- an existing or future permissive policy that grants a wider audience access.
DROP POLICY IF EXISTS bookings_approved_staff_gate ON public.bookings;
CREATE POLICY bookings_approved_staff_gate
ON public.bookings AS RESTRICTIVE FOR ALL TO PUBLIC
USING ((SELECT public.is_pwanistays_admin()))
WITH CHECK ((SELECT public.is_pwanistays_admin()));

DROP POLICY IF EXISTS bookings_approved_staff_access ON public.bookings;
CREATE POLICY bookings_approved_staff_access
ON public.bookings FOR ALL TO authenticated
USING ((SELECT public.is_pwanistays_admin()))
WITH CHECK ((SELECT public.is_pwanistays_admin()));

COMMIT;

-- Confirm access with the approved account, an unapproved account and a signed-out client.
-- Privileged database roles can still manage records. Keep service-role keys private.
