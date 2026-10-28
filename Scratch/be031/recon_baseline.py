"""BE-031 §3 read-only baseline recon. Genuinely read-only: psycopg2 readonly
session, SELECT-only SQL. No DDL/DML, no migration, no hatch, never prints a URL.

Inspects pofa_test (TEST url) and pofa_dev (.env DATABASE_URL) for: target
identity, alembic revision, audit-ledger chain state + enforcement catalog +
TRUNCATE privilege model, and users.external_subject shape.
"""
from __future__ import annotations
import json, re, sys
import psycopg2

def load_env_url(path, key="DATABASE_URL"):
    txt = open(path, encoding="utf-8").read()
    m = re.search(rf'^{key}\s*=\s*(.+?)\s*$', txt, re.MULTILINE)
    v = m.group(1).strip().strip('"').strip("'")
    return v

def to_dsn(url):
    return url.replace("postgresql+psycopg2://", "postgresql://")

def connect(dsn):
    c = psycopg2.connect(dsn)
    c.set_session(readonly=True, autocommit=False)  # hard read-only, no writes
    return c

def q(cur, sql, params=None):
    cur.execute(sql, params or {})
    return cur.fetchall()

def inspect(dsn, expect):
    out = {"expected": expect}
    c = connect(dsn)
    cur = c.cursor()
    out["current_database"] = q(cur, "SELECT current_database()")[0][0]
    out["server_version"] = q(cur, "SHOW server_version")[0][0]
    # alembic revision
    try:
        out["alembic_version"] = [r[0] for r in q(cur, "SELECT version_num FROM alembic_version")]
    except Exception as e:
        c.rollback()
        out["alembic_version"] = f"<err {e}>"
    # audit ledger span
    out["ledger"] = dict(zip(
        ["rows","min_seq","max_seq","distinct_seq","span_minus_count"],
        q(cur, "SELECT count(*), min(sequence_number), max(sequence_number),"
                " count(DISTINCT sequence_number),"
                " max(sequence_number)-count(DISTINCT sequence_number)"
        " FROM audit_ledger_events")[0]))
    # gap RANGE count = transitions where consecutive sequences differ by >1
    gaps = q(cur,
        "SELECT count(*) FROM (SELECT sequence_number -"
        " lag(sequence_number) OVER (ORDER BY sequence_number) d"
        " FROM audit_ledger_events) x WHERE d > 1")
    out["gap_range_count"] = gaps[0][0]
    # out-of-domain / null event_type
    out["null_event_type"] = q(cur,
        "SELECT count(*) FROM audit_ledger_events WHERE event_type IS NULL")[0][0]
    # enforcement catalog
    out["trigger_present"] = bool(q(cur,
        "SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid"
        " JOIN pg_namespace n ON n.oid=c.relnamespace"
        " WHERE t.tgname='trg_audit_ledger_append_only' AND c.relname='audit_ledger_events'"
        " AND n.nspname='public' AND NOT t.tgisinternal"))
    out["function_present"] = bool(q(cur,
        "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace"
        " WHERE p.proname='audit_ledger_refuse_mutation' AND n.nspname='public'"))
    out["check_present"] = bool(q(cur,
        "SELECT 1 FROM pg_constraint WHERE conname='ck_audit_ledger_event_type_domain'"))
    # TRUNCATE privilege model
    out["table_owner"] = q(cur,
        "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.audit_ledger_events'::regclass")[0][0]
    out["session_user"] = q(cur, "SELECT current_user")[0][0]
    out["login_user"] = q(cur, "SELECT session_user")[0][0]
    out["has_truncate_priv"] = q(cur,
        "SELECT has_table_privilege(current_user,'public.audit_ledger_events','TRUNCATE')")[0][0]
    out["is_owner_of_table"] = (out["table_owner"] == out["session_user"])
    out["role_memberships"] = q(cur,
        "SELECT r.rolname FROM pg_roles r"
        " JOIN pg_auth_members m ON m.roleid=r.oid"
        " JOIN pg_roles u ON u.oid=m.member"
        " WHERE u.rolname=current_user")
    # users external_subject shape
    try:
        out["users_total"] = q(cur, "SELECT count(*) FROM users")[0][0]
        out["external_subject_null"] = q(cur,
            "SELECT count(*) FROM users WHERE external_subject IS NULL")[0][0]
        out["distinct_identity_provider"] = [r[0] for r in q(cur,
            "SELECT DISTINCT identity_provider FROM users")]
        out["uq_def"] = q(cur,
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conname='uq_user_identity_subject'")[0][0]
    except Exception as e:
        c.rollback()
        out["users_err"] = str(e)
    cur.close(); c.close()
    return out

def main():
    root = "D:/CODING/Projects/Proof-Of-Action-Final"
    test_dsn = to_dsn(open("D:/CODING/Scratch/be030/_testurl.txt", encoding="utf-8").read().strip())
    dev_dsn = to_dsn(load_env_url(f"{root}/.env"))
    report = {}
    for label, dsn, expect in [("pofa_test", test_dsn, "pofa_test"),
                               ("pofa_dev", dev_dsn, "pofa_dev")]:
        try:
            r = inspect(dsn, expect)
            r["target_matches_expectation"] = (r.get("current_database") == expect)
            report[label] = r
        except Exception as e:
            report[label] = {"expected": expect, "error": repr(e)}
    print(json.dumps(report, indent=1, default=str))

if __name__ == "__main__":
    main()
