"""BE-037 Phase B Stage H (run F) — the remaining database-security edges.

Two of run B1's rows were refusals for the wrong reason and are re-measured here:
  * the catalogue-view test used a column that does not exist, so it proved nothing;
  * the "delete from an ordinary table" test asserted a denial that the F-05 grant
    shape deliberately does NOT grant, so it was mis-scoped, not failing.
Plus one scope question the earlier runs leave open: is any of this enforced by
row-level security, or only by grants plus application code?
"""
import os

import psycopg2

DSN = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", str(detail)))
    print(("PASS  " if ok else "FAIL  ") + name + "  | " + str(detail)[:240], flush=True)


conn = psycopg2.connect(DSN)
conn.autocommit = False
cur = conn.cursor()


def one(sql, label):
    try:
        cur.execute(sql)
        try:
            rows = cur.fetchall()
            conn.rollback()
            print(f"   {label}: ALLOWED {str(rows)[:180]}", flush=True)
            return "ALLOWED", str(rows), "None"
        except Exception:
            n = cur.rowcount
            conn.rollback()
            print(f"   {label}: ALLOWED ({n} rows)", flush=True)
            return "ALLOWED", f"{n} rows", "None"
    except psycopg2.Error as err:
        text = str(err).strip().splitlines()[0]
        cls = type(err).__name__
        conn.rollback()
        print(f"   {label}: REFUSED [{cls}] {text[:180]}", flush=True)
        return "REFUSED", text, cls


print("=== H17 superuser-only catalogue views ===")
st, d, c = one("SELECT rolname, rolpassword FROM pg_authid LIMIT 1", "pg_authid read")
check("H17 the runtime cannot read pg_authid (the real credential hash view), "
      "and is refused for the right reason",
      st == "REFUSED" and c in ("InsufficientPrivilege", "ProgrammingError")
      and "permission denied" in d, f"[{c}] {d}")

st, d, c = one("SELECT role_name, pg_get_functiondef(oid) FROM pg_proc "
               "WHERE proname='audit_ledger_refuse_mutation'", "read enforcement fn body")
print(f"   (informational) reading the enforcement function definition: {st}", flush=True)

print()
print("=== H18 ordinary business tables: what the runtime identity is trusted to do ===")
st, d, c = one("DELETE FROM organizations WHERE id = "
               "(SELECT id FROM organizations ORDER BY id LIMIT 1)", "delete one org (rolled back)")
print("   SCOPE STATEMENT: this is ALLOWED BY DESIGN. The F-05 grant shape gives the "
      "runtime full DML on ordinary tables; only audit_ledger_events (and "
      "alembic_version) are INSERT-only. Append-only therefore protects the ledger, "
      "not the business rows it describes.", flush=True)

st, d, c = one("UPDATE organizations SET name=name WHERE id = "
               "(SELECT id FROM organizations ORDER BY id LIMIT 1)", "no-op update on a business table")
check("H18 the runtime keeps normal write access to business tables (by design; "
      "statement rolled back, nothing persisted)",
      st == "ALLOWED", f"[{c}] {d}")

st, d, c = one("SELECT count(*), max(sequence_number) FROM audit_ledger_events", "ledger head")
check("H18 after every write attempt above the ledger is still 87 rows at head 87",
      st == "ALLOWED" and d.strip() == "[(87, 87)]", d)

print()
print("=== H19 is any of this row-level security, or only grants + application code? ===")
st, d, c = one("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
               "WHERE n.nspname='public' AND c.relrowsecurity ORDER BY 1", "RLS-enabled tables")
print(f"   tables with ROW SECURITY enabled: {d if st=='ALLOWED' else st}", flush=True)
check("H19 no table uses PostgreSQL row-level security — multi-tenant scoping is an "
      "application-layer control, so a DB-level privilege finding would not be "
      "mitigated by RLS",
      st == "ALLOWED" and d.strip() == "[]", d)

st, d, c = one("SELECT polname FROM pg_policy LIMIT 5", "policies")
print(f"   RLS policies present: {d if st=='ALLOWED' else st}", flush=True)

st, d, c = one("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
               "AND tgrelid='audit_ledger_events'::regclass", "trigger names")
check("H19 exactly the one expected trigger, trg_audit_ledger_append_only",
      st == "ALLOWED" and d.strip() == "[('trg_audit_ledger_append_only',)]", d)

print()
print("=== SUMMARY ===")
for n, s, dd in RESULTS:
    if s == "FAIL":
        print("FAILING CHECK:", n, "|", str(dd)[:200])
t = len(RESULTS)
p = sum(1 for _, s, _ in RESULTS if s == "PASS")
print(f"H4_RESULT: total={t} pass={p} fail={t-p}")
