-- BE-032R F-05: least-privilege, non-owner runtime role for the PoA backend.
--
-- WHY THIS EXISTS
--   BE-030's refusing trigger blocks UPDATE/DELETE on the audit ledger, but a
--   `FOR EACH ROW` trigger does NOT fire on `TRUNCATE`. While the application
--   connects as the schema/table OWNER (historically `postgres`), it could wipe
--   the whole ledger and `verify_chain` would then re-baseline a fresh chain from
--   sequence 1 and report `valid=True` -- the measured TRUNCATE hole (BE-030 §2f,
--   BE-032 F-05). A trigger cannot close an owner-only privilege. Only removing
--   ownership from the runtime connection does.
--
-- WHAT THIS DOES
--   Creates a `poa_runtime` LOGIN role that is NOT the table owner and holds
--   exactly the privileges ordinary request code needs, and separates it from the
--   migration/administrative identity (`poa_migrator`) that owns the schema. The
--   application connects as `poa_runtime`; only Alembic/DDL uses `poa_migrator`.
--
--   On a non-owner `poa_runtime` connection the ledger is:
--     * INSERT allowed  -> authorized appends keep working;
--     * UPDATE/DELETE   -> denied by the permission layer (42501) *before* the
--                          trigger is even reached: defense in depth, and it no
--                          longer depends on the hatch GUC being unset;
--     * TRUNCATE        -> denied because TRUNCATE requires table ownership, which
--                          `poa_runtime` does not have. THIS is the F-05 fix.
--   `poa_runtime` is granted no membership in `poa_migrator`/owner roles, so it
--   cannot `SET ROLE` its way back to ownership (proven in BE-032R §Phase C).
--
-- HOW TO APPLY (explicit operational authorization required -- NOT for pytest):
--   1. Run as a role that OWNS the schema objects (the migration identity). In the
--      current single-owner deployment that is `postgres`; in the target design it
--      is `poa_migrator`.
--   2. Supply the runtime password out-of-band -- it is never written here:
--         PGSSLMODE / pgpass, or:
--         PGPASSWORD=... ; psql -v runtime_password="'$PGPASSWORD'" ...
--      The script reads the password from the `:runtime_password` psql variable.
--   3. Point DATABASE_URL at the intended (disposable OR approved live) database.
--      DO NOT run against a database unless the live operational approval is held;
--      this repo's protected-database rules apply unchanged.
--
-- This script is idempotent: re-running it converges on the same grants.

\set ON_ERROR_STOP on

-- The runtime password is passed in, never embedded. If the variable is unset the
-- ALTER below fails loudly rather than silently creating an open role.
\if :{?runtime_password}
\else
  \echo 'ERROR: pass -v runtime_password='''' (single-quoted) -- refusing to create an open role'
  \q
\endif

-- ---------------------------------------------------------------------------
-- Roles
-- ---------------------------------------------------------------------------
-- `poa_migrator` owns the schema and performs DDL. `poa_runtime` is the app
-- identity. Neither is superuser. NOCREATEROLE/NOBYPASSRLS on the runtime role so
-- it cannot mint privileges or bypass row-level policy.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'poa_runtime') THEN
    CREATE ROLE poa_runtime LOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END
$$;

-- The password is set at top level (not inside the DO block) because psql does
-- not substitute :variables inside dollar-quoted strings.
ALTER ROLE poa_runtime WITH PASSWORD :runtime_password;

-- ---------------------------------------------------------------------------
-- Schema access: the runtime role can USE the schema but not CREATE in it.
-- ---------------------------------------------------------------------------
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO poa_runtime;

-- ---------------------------------------------------------------------------
-- Ordinary application tables: full DML. The ledger is handled separately below.
-- Owner (the migrator identity) keeps DDL by virtue of ownership; the runtime role
-- is granted only data privileges, so it cannot ALTER/DROP anything.
-- ---------------------------------------------------------------------------
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
      'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO poa_runtime',
      r.relname);
  END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- The append-only ledger: INSERT + SELECT ONLY. No UPDATE/DELETE/TRUNCATE grant.
-- Combined with non-ownership this is what closes F-05: TRUNCATE needs ownership.
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT ON TABLE public.audit_ledger_events TO poa_runtime;

-- ---------------------------------------------------------------------------
-- Sequences the application advances. The ledger uses a Python-side max+1 under an
-- advisory lock (no DB sequence), but any other sequence the runtime writes to must
-- be granted here. Owner of the sequence is the migrator; runtime gets USAGE/SELECT.
-- ---------------------------------------------------------------------------
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
      'GRANT USAGE, SELECT ON SEQUENCE public.%I TO poa_runtime', r.relname);
  END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- Self-check: print the effective ledger privileges. Expected:
--   insert=t | update=f | delete=f | truncate=f
-- Anything else means the grants did not land as designed.
-- ---------------------------------------------------------------------------
SELECT
  has_table_privilege('poa_runtime', 'audit_ledger_events', 'INSERT')   AS insert_ok,
  has_table_privilege('poa_runtime', 'audit_ledger_events', 'UPDATE')   AS update_ok,
  has_table_privilege('poa_runtime', 'audit_ledger_events', 'DELETE')   AS delete_ok,
  has_table_privilege('poa_runtime', 'audit_ledger_events', 'TRUNCATE') AS truncate_ok;
