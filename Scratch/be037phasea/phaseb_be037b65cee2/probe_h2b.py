"""BE-037 Phase B Stage H (run B2) — corrected privilege matrix + escalation chain.

Why this re-run exists (kept in the record deliberately):
  * run B1's ledger INSERT probes used `'a'*64`, which PostgreSQL parses as
    integer multiplication, so every one of them failed with
    `invalid input syntax for type integer` instead of the constraint under test.
    Those rows were VACUOUS, not evidence. Here the hash literals use repeat() and
    every refusal is asserted against its expected error class, so a pass for the
    wrong reason is reported as a FAIL.
  * run B1 reported `GRANT UPDATE ON audit_ledger_events TO be037b_rt` as ALLOWED.
    The post-check proves the ACL is still `be037b_rt=ar` (insert+select only),
    so the statement was rolled back with its transaction. Whether the grant is
    *effective inside its own transaction* is the real question, so section H13
    tests that escalation chain explicitly and rolls back on purpose.

Runs inside the disposable api container as the runtime identity be037b_rt.
"""
import os

import psycopg2

DSN = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", str(detail)))
    print(("PASS  " if ok else "FAIL  ") + name + "  | " + str(detail)[:260], flush=True)


conn = psycopg2.connect(DSN)
conn.autocommit = False
cur = conn.cursor()


def raw(sql):
    """Execute without deciding anything: returns (status, first_error_line,
    exception_class) or (status, rows, 'None') for a read."""
    try:
        cur.execute(sql)
        try:
            rows = cur.fetchall()
            return ("ALLOWED", rows, "None")
        except Exception:
            return ("ALLOWED", f"{cur.rowcount} rows", "None")
    except psycopg2.Error as err:
        return ("REFUSED", str(err).strip().splitlines()[0], type(err).__name__)


def one(sql, label):
    """One statement in one transaction, then ROLLBACK — nothing may persist."""
    st, detail, cls = raw(sql)
    conn.rollback()
    print(f"   {label}: {st} [{cls}] {str(detail)[:200]}", flush=True)
    return st, str(detail), cls


print("=== H7b identity and role attributes, measured one role at a time ===")
st, detail, cls = one("SELECT current_user, session_user", "identity")
check("H7b the runtime session is be037b_rt for both current_user and session_user",
      st == "ALLOWED" and "be037b_rt" in detail and "be037b_owner" not in detail, detail)

st, detail, cls = one("SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls "
                      "FROM pg_roles WHERE rolname='be037b_rt'", "rt attrs")
check("H7b be037b_rt itself is NOT superuser/createrole/createdb/BYPASSRLS",
      st == "ALLOWED" and detail.strip() == "[(False, False, False, False)]", detail)

st, owner_attrs, cls = one("SELECT rolsuper FROM pg_roles WHERE rolname='be037b_owner'",
                           "owner attrs")
print(f"   DISCLOSURE: the disposable migration/owner identity be037b_owner is the "
      f"container's POSTGRES_USER bootstrap role -> rolsuper={owner_attrs}. "
      f"This is a property of the disposable cluster, not of the runtime path under "
      f"test; no application code ever connects as it.", flush=True)

st, acl, cls = one("SELECT relacl::text FROM pg_class WHERE relname='audit_ledger_events'",
                   "ledger acl")
check("H7b the ledger ACL grants the runtime INSERT+SELECT only (ar)",
      st == "ALLOWED" and "be037b_rt=ar/" in acl, acl)

st, ORIG_ROW1, cls = one("SELECT sequence_number, event_type, action "
                         "FROM audit_ledger_events WHERE sequence_number=1",
                         "row 1 baseline")
st, ORIG_HEAD, cls = one("SELECT count(*), max(sequence_number) FROM audit_ledger_events",
                         "ledger head baseline")
print(f"   BASELINE row1={ORIG_ROW1} head={ORIG_HEAD}", flush=True)

print()
print("=== H10b event-type domain CHECK, re-measured with a well-formed row ===")
BASE_INS = ("INSERT INTO audit_ledger_events (id, sequence_number, event_type, action, "
            "resource_type, payload, metadata, previous_hash, event_hash, created_at) "
            "VALUES (gen_random_uuid(), "
            "(SELECT max(sequence_number)+1 FROM audit_ledger_events), "
            "%%ET%%, 'probe', 'probe', '{}'::json, '{}'::json, "
            "repeat('a',64), repeat('b',64), now())")
for label, etype in [
    ("H10b1 out-of-domain event_type", "'BE037B_NOT_A_REAL_EVENT'"),
    ("H10b2 empty event_type", "''"),
    ("H10b3 injection-shaped event_type", "'USER_CREATED; DROP TABLE x--'"),
    ("H10b4 lower-case spelling of a real value", "'user_created'"),
]:
    st, detail, cls = one(BASE_INS.replace("%%ET%%", etype), label)
    # anti-vacuous: the refusal must be the domain CHECK, not a type error
    check(label + " is refused by ck_audit_ledger_event_type_domain",
          st == "REFUSED" and cls == "CheckViolation"
          and "ck_audit_ledger_event_type_domain" in detail,
          f"[{cls}] {detail}")

print()
print("=== H11 re-using a sequence_number cannot fork the chain ===")
st, detail, cls = one(BASE_INS.replace("%%ET%%", "'USER_CREATED'").replace(
    "max(sequence_number)+1", "max(sequence_number)"), "duplicate sequence")
check("H11 duplicate sequence_number is refused by uq_audit_ledger_sequence",
      st == "REFUSED" and cls == "UniqueViolation" and "uq_audit_ledger_sequence" in detail,
      f"[{cls}] {detail}")

st, detail, cls = one(BASE_INS.replace("%%ET%%", "'USER_CREATED'"), "well-formed direct insert")
check("H13precursor: a well-formed direct ledger INSERT by the runtime is ACCEPTED "
      "by the database (prevention of a bad append is the app writer, not the DB)",
      st == "ALLOWED", f"[{cls}] {detail}")
st, after, cls = one("SELECT count(*) FROM audit_ledger_events", "count after rollback")
print(f"   row count after the rolled-back insert: {after} (baseline {ORIG_HEAD})", flush=True)

print()
print("=== H13 privilege-escalation chain, executed inside one rolled-back transaction ===")
print("   question: can the runtime grant itself ledger UPDATE and use it in the same "
      "transaction, defeating append-only?", flush=True)
try:
    def step(sql, note):
        """One attempt inside the shared transaction, isolated by a savepoint so a
        refusal does not abort the transaction and fake the next result."""
        cur.execute("SAVEPOINT probe_sp")
        st, d, c = raw(sql)
        if st == "REFUSED":
            cur.execute("ROLLBACK TO SAVEPOINT probe_sp")
        else:
            cur.execute("RELEASE SAVEPOINT probe_sp")
        print(f"   {note} -> {st} [{c}] {str(d)[:200]}", flush=True)
        return st, str(d), c

    cur.execute("SELECT relacl::text FROM pg_class WHERE relname='audit_ledger_events'")
    print("   step 0 acl at txn start:", str(cur.fetchone()[0])[:120], flush=True)

    st, d, c = step("GRANT UPDATE ON audit_ledger_events TO be037b_rt",
                    "step 1 self-GRANT UPDATE on the ledger")

    st, grant_effective, c = step(
        "SELECT has_table_privilege('be037b_rt','audit_ledger_events','UPDATE')",
        "step 2 has_table_privilege(UPDATE) inside this transaction")

    st, d, c = step("UPDATE audit_ledger_events SET event_type='ORGANIZATION_UPDATED' "
                    "WHERE sequence_number=1",
                    "step 3 ledger UPDATE after the self-grant")
    upd1 = (st, c, d)

    st, d, c = step("SET LOCAL poa.ledger_mutation_exception = 'on'",
                    "step 4 SET LOCAL the sanctioned mutation hatch")

    st, d, c = step("UPDATE audit_ledger_events SET event_type='ORGANIZATION_UPDATED' "
                    "WHERE sequence_number=1",
                    "step 5 ledger UPDATE with the hatch enabled")
    upd2 = (st, c, d)

    if upd2[0] == "ALLOWED":
        cur.execute("SELECT sequence_number, event_type FROM audit_ledger_events "
                    "WHERE sequence_number=1")
        print("   step 6 in-transaction read of the row:", cur.fetchone(), flush=True)
finally:
    conn.rollback()
    print("   transaction ROLLED BACK on purpose — nothing from H13 persists.", flush=True)

print()
print("=== H13 verdicts ===")
check("H13a a ledger UPDATE by the runtime is refused by SOME wall (grants, or the "
      "append-only trigger) even after a self-grant",
      upd1[0] == "REFUSED", f"{upd1[0]} [{upd1[1]}] {upd1[2]}")
check("H13b a ledger UPDATE is still refused when the sanctioned hatch GUC is enabled "
      "in the same session",
      upd2[0] == "REFUSED", f"{upd2[0]} [{upd2[1]}] {upd2[2]}")

print()
print("=== H14 post-state: the escalation attempt changed nothing durable ===")
st, d, c = one("SELECT has_table_privilege('be037b_rt','audit_ledger_events','UPDATE'), "
               "has_table_privilege('be037b_rt','audit_ledger_events','DELETE'), "
               "has_table_privilege('be037b_rt','audit_ledger_events','TRUNCATE'), "
               "has_table_privilege('be037b_rt','audit_ledger_events','INSERT')",
               "privileges after rollback")
check("H14 the self-grant did not persist: runtime still has INSERT only "
      "(expect [False, False, False, True])",
      st == "ALLOWED" and d.startswith("[(False, False, False, True)"), d)
st, d, c = one("SELECT sequence_number, event_type, action FROM audit_ledger_events "
               "WHERE sequence_number=1", "row 1 after rollback")
check("H14 row 1 is byte-identical to the pre-attempt capture",
      st == "ALLOWED" and d == ORIG_ROW1, f"now={d} before={ORIG_ROW1}")
st, d, c = one("SELECT count(*), max(sequence_number) FROM audit_ledger_events", "ledger size")
check("H14 the ledger head is identical to the pre-attempt baseline",
      st == "ALLOWED" and d == ORIG_HEAD, f"now={d} before={ORIG_HEAD}")

print()
print("H13_WALL_VERDICT grant_effective_in_txn=" + str(grant_effective))
print("H13_WALL_VERDICT update_after_self_grant=" + upd1[0] + " class=" + upd1[1])
print("H13_WALL_VERDICT update_with_hatch=" + upd2[0] + " class=" + upd2[1])
print()
print("=== SUMMARY ===")
for n, s, dd in RESULTS:
    if s == "FAIL":
        print("FAILING CHECK:", n, "|", str(dd)[:200])
t = len(RESULTS)
p = sum(1 for _, s, _ in RESULTS if s == "PASS")
print(f"H2B_RESULT: total={t} pass={p} fail={t-p}")
