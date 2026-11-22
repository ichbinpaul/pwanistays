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

-- Bookings can also be exposed through ordinary views that run as their owner
-- or materialized views containing copied rows. Review any accessible results.
with recursive booking_relations (id) as (
    select 'public.bookings'::regclass::oid
    union
    select r.ev_class
    from booking_relations b
    join pg_depend d on d.refclassid = 'pg_class'::regclass and d.refobjid = b.id
        and d.classid = 'pg_rewrite'::regclass
    join pg_rewrite r on r.oid = d.objid
    join pg_class c on c.oid = r.ev_class and c.relkind in ('v', 'm')
)
select c.oid::regclass as dependent_view, c.relkind as view_type,
       coalesce('security_invoker=true' = any(c.reloptions), false) as security_invoker,
       has_any_column_privilege('anon', c.oid, 'SELECT') as anon_can_read,
       has_any_column_privilege('authenticated', c.oid, 'SELECT') as signed_in_can_read
from booking_relations b join pg_class c on c.oid = b.id
where c.relkind in ('v', 'm')
order by dependent_view;

-- Identify routines that name bookings directly. Also review integrations or
-- dynamic SQL separately if they expose data through another table or service.
select p.oid::regprocedure as routine, p.prosecdef as security_definer,
       has_function_privilege('anon', p.oid, 'EXECUTE') as anon_can_call,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') as signed_in_can_call
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname not in ('pg_catalog', 'information_schema')
  and case when p.prokind in ('f', 'p') then pg_get_functiondef(p.oid) ~* '\mbookings\M' else false end
order by routine;
