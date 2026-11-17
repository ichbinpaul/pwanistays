-- Inspect grants & RLS after changes. READ ONLY.
select tablename, policyname, roles, cmd, qual, with_check from pg_policies
where schemaname='public' and tablename in ('properties','reviews','inquiries','bookings')
order by tablename,policyname;
select table_name, column_name, grantee, privilege_type
from information_schema.column_privileges
where table_schema='public' and table_name='properties' and grantee in ('anon','authenticated')
order by grantee,column_name;
select table_name, grantee, privilege_type
from information_schema.role_table_grants
where table_schema='public' and table_name in ('properties','reviews','inquiries','bookings') and grantee in ('anon','authenticated')
order by table_name,grantee;
