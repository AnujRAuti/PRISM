"""BE-029 scratch: dump the exact retirement set (all columns, ordered) to JSON.

Usage: python snap.py <outfile>
Read-only against the target database. Used to prove that downgrade() restores
every column value literally, not approximately.
"""
import json, os, sys
import psycopg2
from psycopg2.extras import RealDictCursor

OUT = sys.argv[1]
CURI = os.environ.get(
    "BE029_DB", "postgresql://postgres:postgres@localhost:5432/pofa_be029_scratch")
Q = {
 "users": "SELECT u.* FROM users u WHERE u.username='testuser' AND u.email='test@example.com' ORDER BY u.id",
 "projects": "SELECT p.* FROM projects p WHERE p.owner_id IN (SELECT id FROM users WHERE username='testuser' AND email='test@example.com') ORDER BY p.id",
 "evidence": "SELECT e.* FROM evidence e WHERE e.project_id IN (SELECT p.id FROM projects p WHERE p.owner_id IN (SELECT id FROM users WHERE username='testuser' AND email='test@example.com')) ORDER BY e.id",
}
snap = {}
c = psycopg2.connect(CURI); c.set_session(readonly=True, autocommit=True)
cur = c.cursor(cursor_factory=RealDictCursor)
for name, sql in Q.items():
    cur.execute("SELECT ST_IsNull(location) IS NULL AS has_geo FROM evidence LIMIT 0") if False else None
    cur.execute(sql.replace("e.*", "e.*, ST_AsText(e.location) AS location_wkt") if name == "evidence" else sql)
    rows = []
    for r in cur.fetchall():
        rows.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()})
    snap[name] = rows
counts = {}
for t in ("users","projects","evidence","audit_ledger_events","claims","activities","review_cases","user_role_assignments","evidence_metadata","analysis_jobs"):
    cur.execute(f'SELECT count(*) AS n FROM "{t}"'); counts[t] = cur.fetchone()["n"]
dup = {}
for col in ("username","email"):
    cur.execute(f'SELECT {col}, count(*) AS n FROM users GROUP BY {col} HAVING count(*)>1 ORDER BY 1')
    dup[col] = cur.fetchall()
cur.execute("SELECT current_database()")
database = cur.fetchone()["current_database"]
out = {"database": database,
       "snapshot": snap, "table_counts": counts, "duplicate_groups": dup}
json.dump(out, open(OUT, "w"), indent=1, default=str)
print(OUT, "candidates:", {k: len(v) for k, v in snap.items()})
print("tables:", counts)
print("dup groups:", {k: [(r["username"] if k=="username" else r["email"], r["n"]) for r in v] for k, v in dup.items()})
