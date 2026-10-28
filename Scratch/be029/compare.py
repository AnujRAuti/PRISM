"""BE-029 scratch: compare a set of live rows or archive snapshots against the
pre-upgrade snapshot captured by snap.py.

Usage: python compare.py <pre_upgrade.json> <mode>
  mode = archive   -> compare identity_retirement_archive.row_json to the snapshot
  mode = restored  -> compare the live rows (after downgrade) to the snapshot

Read-only. Proves §29's "restore the rows literally" instead of asserting it.
"""
import json
import os
import sys
from datetime import datetime

import psycopg2


def canonical_timestamp(text_value):
    """Parse an ISO-8601 timestamp and re-emit it with padded microseconds.

    jsonb renders '...7389+00:00' where Python's isoformat() renders
    '...738900+00:00'; both are the same instant, so compare parsed values.
    """
    try:
        parsed = datetime.fromisoformat(text_value)
    except ValueError:
        return text_value
    return parsed.isoformat(timespec="microseconds")


PRE, MODE = sys.argv[1], sys.argv[2]
DB = os.environ.get(
    "BE029_DB", "postgresql://postgres:postgres@localhost:5432/pofa_be029_scratch")
data = json.load(open(PRE))
snap = data["snapshot"]
print(f"database: {DB.rsplit('/', 1)[-1]}")

def norm(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return repr(value)
    if hasattr(value, "isoformat"):
        return canonical_timestamp(value.isoformat())
    return canonical_timestamp(str(value))

def flatten(row, skip=()):
    return {k: norm(v) for k, v in row.items() if k not in skip}

live = {}
if MODE == "restored":
    con = psycopg2.connect(DB); con.set_session(readonly=True, autocommit=True)
    cur = con.cursor()
    for table in ("users", "projects", "evidence"):
        ids = [r["id"] for r in snap[table]]
        cur.execute(f"SELECT * FROM {table} WHERE id = ANY(%s::uuid[])", (ids,))
        names = [d[0] for d in cur.description]
        live[table] = {str(r[0]): dict(zip(names, r)) for r in cur.fetchall()}
    source = "live rows"
    get = lambda table, rid: live[table].get(rid)
    skip = ()
else:
    con = psycopg2.connect(DB); con.set_session(readonly=True, autocommit=True)
    cur = con.cursor()
    cur.execute("SELECT source_table, source_id, row_json FROM identity_retirement_archive")
    archived = {}
    for source_table, source_id, row_json in cur.fetchall():
        archived[(source_table, str(source_id))] = row_json
    source = "archive snapshots"
    get = lambda table, rid: archived.get((table, rid))
    skip = ("location_wkt",)

problems = []
checked = 0
for table, rows in snap.items():
    for row in rows:
        rid = str(row["id"])
        other = get(table, rid)
        if other is None:
            problems.append(f"{table} {rid}: missing from {source}")
            continue
        a, b = flatten(row, skip=("location_wkt",)), flatten(other)
        # geometry is carried differently through jsonb than through psycopg2;
        # all candidate rows are NULL, which is asserted explicitly below.
        if a.get("location") != b.get("location"):
            problems.append(f"{table} {rid}: location {a.get('location')} != {b.get('location')}")
        a.pop("location", None); b.pop("location", None)
        if a != b:
            diff = {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
            problems.append(f"{table} {rid}: column differences {diff}")
        checked += 1

print(f"mode={MODE} compared {checked} rows against {PRE}")
print(f"geometry values all NULL: {all(r.get('location') is None for rows in snap.values() for r in rows)}")
if problems:
    print(f"DIFFERENCES ({len(problems)}):")
    for p in problems[:20]:
        print("  -", p)
    sys.exit(1)
print("IDENTICAL: every column value matches the pre-upgrade snapshot")
