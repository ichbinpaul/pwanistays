-- Run this one-time cleanup in the PwaniStays Supabase SQL Editor.
-- It standardizes legacy No Name and NA placeholders without changing booking locations or amounts.
WITH updated AS (
    UPDATE public.bookings
    SET unit_name = 'N/A'
    WHERE lower(trim(regexp_replace(unit_name, '[[:space:]]+', ' ', 'g'))) IN ('no name', 'na')
    RETURNING id
)
SELECT count(*) AS bookings_updated FROM updated;
