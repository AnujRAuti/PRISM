"""Phase 3/5: full read-only state snapshot of one database, as JSON.

Usage: BE029_DB=<postgres-url> python rb_state.py <out.json>

Captures everything the reversibility proof turns on, at three depths:

* every table  -- row count and an order-independent content fingerprint
* users/projects/evidence -- the complete row images, keyed by primary key, so
  a comparison is a comparison of column values and not of counts
* identity_retirement_archive -- all rows, with the json payloads verbatim
plus the alembic revision, the users index and constraint definitions, the
duplicate groups, and the residue count.
"""
import json
import os
import sys

import psycopg2
from psycopg2 import extras

DB = os.environ.get("BE029_DB")
if not DB:
    sys.exit("set BE029_DB to the postgres URL to snapshot")
OUT = sys.argv[1]

state = {"current_database": None, "alembic_version": None, "table_fingerprints": {},
         "row_images": {}, "index_definitions": {}, "constraint_definitions": {},
         "duplicate_groups": {}, "residue_users": None, "archive": None,
         "ledger": None}

conn = psycopg2.connect(DB)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=extras.RealDictCursor)

cur.execute("SELECT current_database() AS d")
state["current_database"] = cur.fetchone()["d"]
cur.execute("SELECT coalesce(string_agg(version_num, ','), '(none)') AS v FROM alembic_version")
state["alembic_version"] = cur.fetchone()["v"]

cur.execute("SELECT c.relname AS t FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace"
            " WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY 1")
tables = [r["t"] for r in cur.fetchall()]
for t in tables:
    cur.execute(f'SELECT count(*) AS n FROM "public"."{t}"')
    n = cur.fetchone()["n"]
    cur.execute(f"SELECT md5(string_agg(x::text, E'\\n' ORDER BY x::text)) AS fp"
                f" FROM \"public\".\"{t}\" x")
    state["table_fingerprints"][t] = {"rows": n, "fingerprint": cur.fetchone()["fp"]}

for t in ("users", "projects", "evidence"):
    cur.execute(f"SELECT id, row_to_json(x) AS j FROM \"public\".{t} x ORDER BY id::text")
    state["row_images"][t] = {r["id"]: r["j"] for r in cur.fetchall()}

cur.execute("SELECT indexname, indexdef AS def FROM pg_indexes"
            " WHERE schemaname='public' AND tablename='users' ORDER BY indexname")
state["index_definitions"] = {r["indexname"]: r["def"] for r in cur.fetchall()}

cur.execute("SELECT conname, pg_get_constraintdef(c.oid, true) AS def FROM pg_constraint c"
            " JOIN pg_class t ON t.oid=c.conrelid"
            " WHERE t.relname='users' AND c.contype IN ('p','u','c') ORDER BY conname")
state["constraint_definitions"] = {r["conname"]: r["def"] for r in cur.fetchall()}

for col in ("username", "email"):
    cur.execute(f'SELECT {col} AS value, count(*) AS n FROM users'
                f' GROUP BY {col} HAVING count(*) > 1 ORDER BY 1')
    state["duplicate_groups"][col] = cur.fetchall()

cur.execute("SELECT count(*) AS n FROM users WHERE username='testuser'"
            " AND email='test@example.com'")
state["residue_users"] = cur.fetchone()["n"]

cur.execute("SELECT to_regclass('public.identity_retirement_archive') AS r")
if cur.fetchone()["r"]:
    cur.execute("SELECT source_table, source_id, row_json, retired_at"
                " FROM identity_retirement_archive"
                " ORDER BY source_table, source_id::text")
    state["archive"] = [{"source_table": r["source_table"], "source_id": str(r["source_id"]),
                         "row_json": r["row_json"],
                         "retired_at": r["retired_at"].isoformat()} for r in cur.fetchall()]

cur.execute("SELECT count(*) AS n, min(sequence_number) AS lo, max(sequence_number) AS hi"
            " FROM audit_ledger_events")
state["ledger"] = cur.fetchone()

json.dump(state, open(OUT, "w"), indent=1, default=str)
print(f"snapshot of {state['current_database']} at {state['alembic_version']} -> {OUT}")
print(f"  tables={len(tables)} users={len(state['row_images']['users'])}"
      f" projects={len(state['row_images']['projects'])}"
      f" evidence={len(state['row_images']['evidence'])}"
      f" archive_rows={0 if state['archive'] is None else len(state['archive'])}"
      f" residue_users={state['residue_users']} ledger={state['ledger']['n']}")
conn.close()
