-- BE-037 Phase B Stage H (run C) — the SECOND wall, measured from the owner side.
--
-- Run B proved the runtime identity is stopped by GRANTS. That leaves the
-- question the trigger exists to answer: what happens to a principal that DOES
-- hold UPDATE/DELETE on the ledger? Only be037b_owner qualifies here, so that is
-- the identity used — and every statement below is inside a transaction that ends
-- in ROLLBACK, so the ledger is unchanged when this file finishes.
--
-- TRUNCATE is deliberately NOT attempted as owner: the append-only trigger is
-- BEFORE UPDATE OR DELETE only, so TRUNCATE would not be refused by it and the
-- damage would be unrecoverable. That case is recorded as NOT RUN with a reason.

\set ON_ERROR_STOP off

BEGIN;

\echo '=== H15a owner UPDATE on the ledger, no hatch: expect the trigger to refuse ==='
DO $do$
BEGIN
    BEGIN
        UPDATE audit_ledger_events SET event_type='ORGANIZATION_UPDATED'
          WHERE sequence_number=1;
        RAISE NOTICE 'RESULT H15a: ALLOWED -> second wall FAILED';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'RESULT H15a: REFUSED sqlstate=% : %', SQLSTATE, SQLERRM;
    END;
END
$do$;

\echo '=== H15b owner DELETE on the ledger, no hatch: expect the trigger to refuse ==='
DO $do$
BEGIN
    BEGIN
        DELETE FROM audit_ledger_events WHERE sequence_number=1;
        RAISE NOTICE 'RESULT H15b: ALLOWED -> second wall FAILED';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'RESULT H15b: REFUSED sqlstate=% : %', SQLSTATE, SQLERRM;
    END;
END
$do$;

\echo '=== H15c a GRANT by the runtime is inert; the same GRANT by the owner is not ==='
DO $do$
DECLARE
    before boolean;
    after  boolean;
BEGIN
    SELECT has_table_privilege('be037b_rt','audit_ledger_events','UPDATE') INTO before;
    EXECUTE 'GRANT UPDATE ON audit_ledger_events TO be037b_rt';
    SELECT has_table_privilege('be037b_rt','audit_ledger_events','UPDATE') INTO after;
    RAISE NOTICE 'RESULT H15c: owner GRANT UPDATE -> runtime privilege % -> %', before, after;
    -- undo it inside this same transaction so nothing persists
    EXECUTE 'REVOKE UPDATE ON audit_ledger_events FROM be037b_rt';
    SELECT has_table_privilege('be037b_rt','audit_ledger_events','UPDATE') INTO after;
    RAISE NOTICE 'RESULT H15c: after REVOKE (same txn) -> %', after;
END
$do$;

\echo '=== H15d the sanctioned hatch path works for a principal that holds the grant ==='
DO $do$
BEGIN
    SET LOCAL poa.ledger_mutation_exception = 'on';
    UPDATE audit_ledger_events SET event_type='ORGANIZATION_UPDATED'
      WHERE sequence_number=1;
    RAISE NOTICE 'RESULT H15d: hatch UPDATE ALLOWED for a granting principal '
                 '(this is the intended remediation path; rolled back below)';
    RESET poa.ledger_mutation_exception;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'RESULT H15d: REFUSED sqlstate=% : %', SQLSTATE, SQLERRM;
END
$do$;

SELECT sequence_number, event_type FROM audit_ledger_events WHERE sequence_number=1;

ROLLBACK;

\echo '=== H16 post-ROLLBACK: nothing above persisted ==='
SELECT count(*) AS ledger_rows, max(sequence_number) AS head FROM audit_ledger_events;
SELECT event_type AS row1_event_type FROM audit_ledger_events WHERE sequence_number=1;
SELECT relacl::text AS ledger_acl FROM pg_class WHERE relname='audit_ledger_events';
SELECT has_table_privilege('be037b_rt','audit_ledger_events','UPDATE') AS rt_update,
       has_table_privilege('be037b_rt','audit_ledger_events','DELETE') AS rt_delete,
       has_table_privilege('be037b_rt','audit_ledger_events','TRUNCATE') AS rt_truncate,
       has_table_privilege('be037b_rt','audit_ledger_events','INSERT') AS rt_insert;

\echo '=== H17 the superuser-only catalogue view really is closed to the runtime ==='
-- run as the runtime identity below in a separate command, not here
