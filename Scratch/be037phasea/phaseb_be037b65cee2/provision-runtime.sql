-- BE-037 Phase B — DISPOSABLE-ONLY runtime role provisioning.
--
-- Adapted from scripts/provision_runtime_roles.sql (BE-032R F-05 grant shape).
-- Deliberate differences, required by the Phase B safety rules:
--   * the role is named for this run (be037b_rt), never `poa_runtime`. Roles are
--     CLUSTER-wide, so the upstream `ALTER ROLE poa_runtime WITH PASSWORD ...`
--     (line 69) would silently break the live development application. This file
--     contains no reference to `poa_runtime` or `poa_migrator` at all.
--   * it runs only inside the Phase B disposable PostgreSQL container, which is
--     its own cluster and is deleted with this run.
--   * it is idempotent and refuses to run if the password variable is unset, so it
--     cannot create an open role.
--
-- It is applied AFTER `alembic upgrade head`, so the tables exist and the grant
-- loops see them. The schema owner here is be037b_owner (the migration identity);
-- be037b_rt is never an owner, which is what closes the F-05 TRUNCATE hole.

\set ON_ERROR_STOP on

\if :{?runtime_password}
\else
  \echo 'ERROR: pass -v runtime_password='''' -- refusing to create an open role'
  \q
\endif

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'be037b_rt') THEN
    CREATE ROLE be037b_rt LOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END
$$;

ALTER ROLE be037b_rt WITH PASSWORD :runtime_password;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO be037b_rt;

-- Ordinary application tables: full DML, no DDL (non-owner).
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relname NOT IN ('audit_ledger_events', 'alembic_version')
  LOOP
    EXECUTE format(
      'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO be037b_rt',
      r.relname);
  END LOOP;
END
$$;

-- Append-only ledger: INSERT + SELECT only.
GRANT SELECT, INSERT ON TABLE public.audit_ledger_events TO be037b_rt;

DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'S'
  LOOP
    EXECUTE format(
      'GRANT USAGE, SELECT ON SEQUENCE public.%I TO be037b_rt', r.relname);
  END LOOP;
END
$$;

-- Self-check. Expected: t | f | f | f
SELECT
  has_table_privilege('be037b_rt', 'audit_ledger_events', 'INSERT')   AS insert_ok,
  has_table_privilege('be037b_rt', 'audit_ledger_events', 'UPDATE')   AS update_ok,
  has_table_privilege('be037b_rt', 'audit_ledger_events', 'DELETE')   AS delete_ok,
  has_table_privilege('be037b_rt', 'audit_ledger_events', 'TRUNCATE') AS truncate_ok;

-- Must print 0 rows: proof this file never created or altered a protected role.
SELECT rolname FROM pg_roles
WHERE rolname IN ('poa_runtime', 'poa_migrator')
ORDER BY rolname;
