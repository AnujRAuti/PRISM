-- BE-037A-D3: grant the disposable runtime role the F-05 least-privilege shape on
-- poa_be037a_disp only (runs after the owner has migrated the schema).
-- Mirrors scripts/provision_runtime_roles.sql but is scoped to this throwaway
-- database/role pair; it never touches poa_runtime or a protected database.

\set ON_ERROR_STOP on
\connect poa_be037a_disp

-- Ordinary application tables: full DML. Ledger handled separately.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
      AND c.relname NOT IN ('audit_ledger_events', 'alembic_version')
  LOOP
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO poa_be037a_rt', r.relname);
  END LOOP;
END
$$;

GRANT SELECT, INSERT ON TABLE public.audit_ledger_events TO poa_be037a_rt;

DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'S'
  LOOP
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.%I TO poa_be037a_rt', r.relname);
  END LOOP;
END
$$;

SELECT
  has_table_privilege('poa_be037a_rt', 'audit_ledger_events', 'INSERT')   AS insert_ok,
  has_table_privilege('poa_be037a_rt', 'audit_ledger_events', 'UPDATE')   AS update_ok,
  has_table_privilege('poa_be037a_rt', 'audit_ledger_events', 'DELETE')   AS delete_ok,
  has_table_privilege('poa_be037a_rt', 'audit_ledger_events', 'TRUNCATE') AS truncate_ok;
