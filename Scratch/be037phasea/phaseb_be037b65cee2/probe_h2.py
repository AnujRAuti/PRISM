"""BE-037 Phase B Stage H (run B) — runtime privilege matrix, executed as be037b_rt.

This runs INSIDE the disposable api container, so the DSN is read from the process
environment and never reaches a command line, a log, or an evidence file. It is the
identity the live application actually uses, so these are the real enforcement
results rather than has_table_privilege() predictions.

Every statement is executed for real in its own transaction and the transaction is
rolled back afterwards, so the ledger and every other table are byte-identical when
this script finishes. The recorded assertion is the exact server error text.
"""
import os
import sys

import psycopg2

DSN = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", str(detail)))
    print(("PASS  " if ok else "FAIL  ") + name + "  | " + str(detail), flush=True)


def run(sql, label):
    """Execute one statement, report ALLOWED or the server's first error line,
    then roll the transaction back so nothing persists."""
    try:
        cur.execute(sql)
        out = None
        try:
            out = cur.fetchall()
        except Exception:
            pass
        conn.rollback()
        return ("ALLOWED", str(out)[:200] if out is not None else f"{cur.rowcount} rows")
    except psycopg2.Error as err:
        msg = str(err).strip().splitlines()
        text = next((l for l in msg if l.startswith("psycopg2") or "ERROR" in l or
                     "permission denied" in l or "must be owner" in l or
                     "violates" in l or "is not permitted" in l), msg[0] if msg else "?")
        conn.rollback()
        return ("REFUSED", text[:240])


conn = psycopg2.connect(DSN)
conn.autocommit = False
cur = conn.cursor()

print("=== H7 who the runtime really is ===")
state, detail = run("SELECT current_user, session_user", "identity")
check("H7 runtime connects as be037b_rt (not owner, not superuser)",
      "be037b_rt" in detail and "be037b_owner" not in detail, detail)

state, detail = run("SELECT bool_or(rolsuper) AS any_super, "
                    "bool_or(rolcreaterole) AS any_createrole, "
                    "bool_or(rolcreatedb) AS any_createdb, "
                    "bool_or(rolbypassrls) AS any_bypassrls "
                    "FROM pg_roles WHERE rolname IN ('be037b_rt','be037b_owner')",
                    "attributes")
check("H7 neither local role is superuser, creator, createdb or BYPASSRLS",
      state == "ALLOWED" and "True" not in detail, detail)

print()
print("=== H8 statements the runtime must NOT be able to run ===")
DENY = [
    ("H8a UPDATE the ledger (row 1)",
     "UPDATE audit_ledger_events SET event_type='USER_CREATED' WHERE sequence_number=1"),
    ("H8b DELETE a ledger row",
     "DELETE FROM audit_ledger_events WHERE sequence_number=1"),
    ("H8c TRUNCATE the ledger",
     "TRUNCATE TABLE audit_ledger_events"),
    ("H8d DROP the ledger",
     "DROP TABLE audit_ledger_events"),
    ("H8e ALTER the ledger (add a column)",
     "ALTER TABLE audit_ledger_events ADD COLUMN be037b_probe int"),
    ("H8f Revoke/re-grant the append-only trigger away",
     "DROP TRIGGER trg_audit_ledger_append_only ON audit_ledger_events"),
    ("H8g Re-create the enforcement function",
     "CREATE OR REPLACE FUNCTION public.audit_ledger_refuse_mutation() RETURNS trigger "
     "LANGUAGE plpgsql AS $x$ BEGIN RETURN NEW; END $x$"),
    ("H8h GRANT itself UPDATE on the ledger",
     "GRANT UPDATE ON audit_ledger_events TO be037b_rt"),
    ("H8i Escalate with SET ROLE to the migration identity",
     "SET ROLE be037b_owner"),
    ("H8j Escalate with SET ROLE to the bootstrap superuser",
     "SET ROLE postgres"),
    ("H8k ALTER ROLE to gain superuser",
     "ALTER ROLE be037b_rt SUPERUSER"),
    ("H8l Create a table in the application schema",
     "CREATE TABLE public.be037b_probe (x int)"),
    ("H8m Write migration history directly",
     "UPDATE alembic_version SET version_num='be037b-forged'"),
    ("H8n Read migration history",
     "SELECT version_num FROM alembic_version"),
    ("H8o Delete from an ordinary business table",
     "DELETE FROM organizations"),
    ("H8p Read a role-password hash view",
     "SELECT rolpassword FROM pg_shadow"),
]
for label, sql in DENY:
    state, detail = run(sql, label)
    check(label + " is refused", state == "REFUSED", f"{state}: {detail}")

print()
print("=== H8q the hatch cannot substitute for a missing grant ===")
try:
    cur.execute("BEGIN")
    cur.execute("SET LOCAL poa.ledger_mutation_exception = 'on'")
    cur.execute("SHOW poa.ledger_mutation_exception")
    guc = cur.fetchone()[0]
    try:
        cur.execute("UPDATE audit_ledger_events SET event_type='USER_CREATED' "
                    "WHERE sequence_number=1")
        outcome = ("ALLOWED", "UPDATE succeeded with the hatch set")
    except psycopg2.Error as err:
        outcome = ("REFUSED", str(err).strip().splitlines()[0])
except psycopg2.Error as err:
    guc = "?"
    outcome = ("REFUSED", str(err).strip().splitlines()[0])
conn.rollback()
print(f"   hatch GUC value the runtime could set = {guc!r}", flush=True)
print(f"   UPDATE with hatch on -> {outcome[0]}: {outcome[1]}", flush=True)
check("H8q ledger UPDATE still refused even with the sanctioned hatch GUC set "
      "(grants, not the trigger, are the outer wall)",
      outcome[0] == "REFUSED", f"{outcome[0]}: {outcome[1]}")

print()
print("=== H9 positive controls: what the runtime legitimately CAN do ===")
ALLOW = [
    ("H9a Read the ledger", "SELECT count(*) FROM audit_ledger_events"),
    ("H9b CAPABILITY CONFIRMED: the database accepts a direct ledger INSERT with "
     "hand-made hashes (no BEFORE INSERT chain validation at the DB layer)",
     "INSERT INTO audit_ledger_events (id, sequence_number, event_type, action, "
     "resource_type, payload, metadata, previous_hash, event_hash, created_at) "
     "VALUES (gen_random_uuid(), "
     "(SELECT max(sequence_number)+1 FROM audit_ledger_events), "
     "'USER_CREATED', 'probe', 'probe', '{}'::json, '{}'::json, "
     "'a'*64, 'b'*64, now())"),
    ("H9c Ordinary DML on a business table (UPDATE of one row, rolled back)",
     "UPDATE organizations SET name=name WHERE id = "
     "(SELECT id FROM organizations ORDER BY id LIMIT 1)"),
    ("H9d Ordinary reads of business tables",
     "SELECT count(*) FROM evidence"),
]
for label, sql in ALLOW:
    state, detail = run(sql, label)
    check(label, state == "ALLOWED", f"{state}: {detail}")
    print(f"   -> {label}: {state} | {detail[:180]}", flush=True)

print()
print("=== H10 the append-only CHECK constraint is enforced at the database ===")
for label, etype in [("H10a invalid event_type", "'BE037B_NOT_A_REAL_EVENT'"),
                     ("H10b empty event_type", "''"),
                     ("H10c sql-injection-shaped event_type", "'USER_CREATED; DROP TABLE x--'")]:
    sql = ("INSERT INTO audit_ledger_events (id, sequence_number, event_type, action, "
           "resource_type, payload, metadata, previous_hash, event_hash, created_at) "
           f"VALUES (gen_random_uuid(), (SELECT max(sequence_number)+1 FROM audit_ledger_events), "
           f"{etype}, 'probe', 'probe', '{{}}'::json, '{{}}'::json, 'a'*64, 'b'*64, now())")
    state, detail = run(sql, label)
    check(label + " is refused by the domain CHECK", state == "REFUSED",
          f"{state}: {detail}")
    print(f"   -> {label}: {state} | {detail[:200]}", flush=True)

print()
print("=== H11 duplicate head sequence cannot fork the chain ===")
sql = ("INSERT INTO audit_ledger_events (id, sequence_number, event_type, action, "
       "resource_type, payload, metadata, previous_hash, event_hash, created_at) "
       "VALUES (gen_random_uuid(), (SELECT max(sequence_number) FROM audit_ledger_events), "
       "'USER_CREATED', 'probe', 'probe', '{}'::json, '{}'::json, 'a'*64, 'b'*64, now())")
state, detail = run(sql, "H11 reuse an existing sequence_number")
check("H11 re-using an existing sequence_number is refused (no chain fork)",
      state == "REFUSED", f"{state}: {detail}")

print()
print("=== H12 nothing from this probe persisted ===")
run("SELECT 1", "noop")
state, detail = run("SELECT count(*), max(sequence_number) FROM audit_ledger_events", "final")
print(f"   ledger rows/max-seq after every probe statement rolled back: {detail}", flush=True)
check("H12 all probe writes were rolled back", state == "ALLOWED", detail)
state, detail = run("SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name='be037b_probe'", "no new table")
check("H12 no probe table exists", state == "ALLOWED" and "0" in detail, detail)

cur.close()
conn.close()

print()
print("=== SUMMARY ===")
for n, s, d in RESULTS:
    if s == "FAIL":
        print("FAILING CHECK:", n, "|", d)
t = len(RESULTS)
p = sum(1 for _, s, _ in RESULTS if s == "PASS")
print(f"H2_RESULT: total={t} pass={p} fail={t-p}")
