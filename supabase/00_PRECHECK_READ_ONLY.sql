-- PwaniStays / Supabase precheck: READ ONLY. Run in SQL Editor before changing permissions.
-- Keep a copy of results. Look for any unexpected broad policies (especially on bookings).
select tablename, policyname, permissive, roles, cmd, qual, with_check
from pg_policies where schemaname='public' and tablename in ('properties','reviews','inquiries','bookings')
order by tablename,policyname;

select table_name, grantee, privilege_type
from information_schema.role_table_grants
where table_schema='public' and table_name in ('properties','reviews','inquiries','bookings')
  and grantee in ('anon','authenticated','PUBLIC')
order by table_name,grantee,privilege_type;

select table_name, column_name, privilege_type, grantee
from information_schema.column_privileges
where table_schema='public' and table_name='properties'
  and grantee in ('anon','authenticated')
order by grantee, column_name;

select c.relname as table_name,c.relrowsecurity as rls_enabled
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relname in ('properties','bookings','reviews','inquiries') and c.relkind='r';
