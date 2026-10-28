"""BE-029 §28 P0 before/after facts for one database, read-only.

Usage: python p0_state.py <postgres-url>
Captures exactly the quantities the BE-029 stop conditions are written in:
residue-group size, duplicate username/email groups, table sizes, the two
uniqueness indexes, the identity constraint definition, and the ledger.
No passwords, tokens, or per-user personal data beyond the fixture values.
"""
import json
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

URL = sys.argv[1]

QUERIES = {
    "current_database": "SELECT current_database() AS n",
    "alembic_version": "SELECT version_num FROM alembic_version",
    "users": "SELECT count(*) AS n FROM users",
    "projects": "SELECT count(*) AS n FROM projects",
    "evidence": "SELECT count(*) AS n FROM evidence",
    "audit_ledger_events": "SELECT count(*) AS n FROM audit_ledger_events",
    "residue_users": (
        "SELECT count(*) AS n FROM users "
        "WHERE username='testuser' AND email='test@example.com'"),
    "residue_projects": (
        "SELECT count(*) AS n FROM projects WHERE name='testproj' AND owner_id IN "
        "(SELECT id FROM users WHERE username='testuser' AND email='test@example.com')"),
    "residue_evidence": (
        "SELECT count(*) AS n FROM evidence WHERE filename='foo.jpg' AND project_id IN "
        "(SELECT p.id FROM projects p WHERE p.owner_id IN "
        "(SELECT id FROM users WHERE username='testuser' AND email='test@example.com'))"),
    "dup_username_groups": (
        "SELECT count(*) AS n FROM (SELECT username FROM users GROUP BY username "
        "HAVING count(*)>1) t"),
    "dup_email_groups": (
        "SELECT count(*) AS n FROM (SELECT email FROM users GROUP BY email "
        "HAVING count(*)>1) t"),
    "dup_username_values": (
        "SELECT username, count(*) AS n FROM users GROUP BY username "
        "HAVING count(*)>1 ORDER BY username"),
    "dup_email_values": (
        "SELECT email, count(*) AS n FROM users GROUP BY email "
        "HAVING count(*)>1 ORDER BY email"),
    "users_indexes": (
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='users' "
        "AND indexname IN ('ix_users_username','ix_users_email') ORDER BY indexname"),
    "users_constraints": (
        "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint "
        "WHERE conrelid='public.users'::regclass ORDER BY conname"),
    "null_external_subject": (
        "SELECT count(*) FILTER (WHERE external_subject IS NULL) AS n_null, "
        "count(*) AS n_total FROM users"),
    "archive_table": (
        "SELECT count(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname='identity_retirement_archive'"),
    "archive_rows": "SELECT count(*) AS n FROM identity_retirement_archive",
    "fk_into_residue": (
        "SELECT 'projects.owner_id' AS ref, count(*) AS n FROM projects p "
        "WHERE p.owner_id IN (SELECT id FROM users WHERE username='testuser' "
        "AND email='test@example.com') "
        "UNION ALL SELECT 'evidence.project_id', count(*) FROM evidence e "
        "WHERE e.project_id IN (SELECT p.id FROM projects p WHERE p.owner_id IN "
        "(SELECT id FROM users WHERE username='testuser' AND email='test@example.com'))"),
}

conn = psycopg2.connect(URL)
conn.set_session(readonly=True, autocommit=True)
out = {}
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    for name, sql in QUERIES.items():
        probe = out.get("archive_table")
        if name == "archive_rows" and isinstance(probe, dict) and not probe.get("n"):
            out[name] = "table absent"
            continue
        try:
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()]
            out[name] = rows[0] if len(rows) == 1 and set(rows[0]) <= {"n"} else rows
        except Exception as exc:  # noqa: BLE001 - report, keep measuring
            conn.rollback()
            out[name] = f"ERROR {type(exc).__name__}: {exc}"
conn.close()

print(json.dumps(out, indent=1, default=str))
