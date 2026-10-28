"""BE-029 Phase 5 item 9/10: prove the live migration changed ONLY the 120
retired rows, by comparing the migrated database against the verified
pre-migration copy restored from the backup.

Usage: python post_verify_diff.py <live-after-url> <pre-migration-copy-url>

Both connections are READ ONLY. Classification, not assumption:
  * tables that exist only after migration must be objects the applied
    revisions create, and must be empty except the retirement archive;
  * tables that existed before must keep the same name set (nothing dropped);
  * every table except users/projects/evidence must have an identical content
    fingerprint -- most importantly audit_ledger_events, which this migration
    must not touch at all;
  * for users/projects/evidence the surviving rows are compared individually:
    before-rows minus the retired ids must equal the after-rows value-for-value.
"""
import json
import re
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

AFTER_URL, BEFORE_URL = sys.argv[1], sys.argv[2]

# The reviewed target set, so the row-by-row subtraction uses exactly the ids
# that were approved for retirement.
with open("D:/CODING/Scratch/be029/preflight_phase3.json") as fh:
    _cands = json.load(fh)["candidates"]
RETIRED = {t: set(_cands[t]) for t in ("users", "projects", "evidence")}


def connect(url):
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    return conn


def rows(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


after, before = connect(AFTER_URL), connect(BEFORE_URL)
ca, cb = after.cursor(cursor_factory=RealDictCursor), before.cursor(cursor_factory=RealDictCursor)


def table_set(cur):
    return {r["t"] for r in rows(cur,
            "SELECT c.relname AS t FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace"
            " WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY 1")}


def fingerprint(cur, t):
    return rows(cur, f'SELECT count(*) AS n, md5(string_agg(x::text, E\'\\n\' ORDER BY'
                     f' x::text)) AS fp FROM "public"."{t}" x')[0]


def images(cur, t):
    return {r["id"]: r["img"] for r in rows(
        cur, f'SELECT id::text AS id, x::text AS img FROM "public"."{t}" x')}


ta, tb = table_set(ca), table_set(cb)
new = sorted(ta - tb)
gone = sorted(tb - ta)
print(f"tables after={len(ta)} before={len(tb)}")
print(f"NEW tables ({len(new)}): {new}")
print(f"DROPPED tables ({len(gone)}): {gone or 'none'}")

problems = []
if gone:
    problems.append(f"tables disappeared: {gone}")

# new tables must be empty except the archive, which holds the 120 retired rows
for t in new:
    n = fingerprint(ca, t)["n"]
    if t == "identity_retirement_archive":
        if int(n) != 120:
            problems.append(f"identity_retirement_archive holds {n} rows, expected 120")
    elif int(n) != 0:
        problems.append(f"new table {t} is not empty ({n} rows) - a data-bearing new"
                        " table cannot be explained by a schema-only revision")

# every pre-existing table except the three retirement inputs must be identical
print("\n--- pre-existing tables, content comparison ---")
diff = []
for t in sorted(tb):
    fa = fingerprint(ca, t) if t in ta else None
    fb = fingerprint(cb, t)
    if fa is None:
        continue
    if fa["fp"] == fb["fp"]:
        continue
    diff.append(t)
    print(f"  DIFFERS {t}: before {fb['n']} rows -> after {fa['n']} rows")
expected_diff = {"users", "projects", "evidence", "alembic_version"}
unexpected = sorted(set(diff) - expected_diff)
if unexpected:
    problems.append(f"tables changed that must not have: {unexpected}")
missing_diff = sorted(expected_diff - set(diff))
if missing_diff:
    problems.append(f"tables that should have changed but are identical: {missing_diff}")
if not unexpected:
    print(f"  all other {len(tb) - len(diff)} pre-existing tables: IDENTICAL content"
          f" (including audit_ledger_events)")

# row-level subtraction for the three affected tables
print("\n--- row-level proof that only the retired rows moved ---")
for t in ("users", "projects", "evidence"):
    ia, ib = images(ca, t), images(cb, t)
    retired_found = sorted(set(ib) & RETIRED[t])
    survivors_before = {k: v for k, v in ib.items() if k not in RETIRED[t]}
    added = sorted(set(ia) - set(ib))
    removed = sorted(set(ib) - set(ia))
    changed = [k for k, v in survivors_before.items()
               if k in ia and ia[k] != v]
    print(f"  {t}: before={len(ib)} after={len(ia)}"
          f" removed={len(removed)} added={len(added)}"
          f" retired_ids_present_before={len(retired_found)}"
          f" surviving_rows_modified={len(changed)}")
    if removed != sorted(RETIRED[t]):
        problems.append(f"{t}: removed ids are not exactly the reviewed retirement set")
    if added:
        problems.append(f"{t}: {len(added)} rows appeared that were not in the backup")
    if changed:
        problems.append(f"{t}: {len(changed)} surviving rows were modified")
    if len(retired_found) != len(RETIRED[t]):
        problems.append(f"{t}: only {len(retired_found)} of {len(RETIRED[t])}"
                        " reviewed ids existed before the migration")

# the archive must be exactly the removed rows, verbatim
print("\n--- archive equals the removed rows ---")
arch = rows(ca, "SELECT source_table, source_id, row_json->>'id' AS rid"
               " FROM identity_retirement_archive ORDER BY 1, 2")
by_table = {}
for r in arch:
    by_table.setdefault(r["source_table"], set()).add(r["rid"])
for t in ("users", "projects", "evidence"):
    got = by_table.get(t, set())
    removed = {k for k, v in images(cb, t).items() if k not in images(ca, t)}
    print(f"  {t}: archived={len(got)} removed_from_live={len(removed)}"
          f" same_ids={got == removed}")
    if got != removed:
        problems.append(f"{t}: archive ids != removed ids")
    if got != RETIRED[t]:
        problems.append(f"{t}: archive ids != reviewed retirement ids")

# index/constraint surface, so the DDL delta is enumerated rather than trusted
print("\n--- index and constraint delta ---")


def idx(cur):
    return {r["indexname"]: r["indexdef"] for r in rows(
        cur, "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public'")}


def con(cur):
    return {f"{r['tbl']}:{r['name']}": r["def"] for r in rows(
        cur, "SELECT conrelid::regclass::text AS tbl, conname AS name,"
             " pg_get_constraintdef(oid) AS def FROM pg_constraint"
             " WHERE connamespace='public'::regnamespace")}


ia_i, ib_i = idx(ca), idx(cb)
ia_c, ib_c = con(ca), con(cb)
print(f"  indexes before={len(ib_i)} after={len(ia_i)}"
      f" added={len(set(ia_i)-set(ib_i))} dropped={len(set(ib_i)-set(ia_i))}")
for name in sorted(set(ia_i) - set(ib_i)):
    m = re.search(r"ON (?:public\.)?(\w+)", ia_i[name])
    owner = m.group(1) if m else "?"
    unique = "UNIQUE" if "UNIQUE INDEX" in ia_i[name] else "plain"
    origin = "table created by this run" if owner in new else "pre-existing table (BE-028/029)"
    print(f"    added {unique:6} {name} on {owner} [{origin}]")
for name in sorted(set(ib_i) - set(ia_i)):
    print(f"    DROPPED index {name}: {ib_i[name]}")
    if name not in {"ix_users_username", "ix_users_email"}:
        problems.append(f"index dropped that BE-029 did not recreate: {name}")
print(f"  constraints before={len(ib_c)} after={len(ia_c)}"
      f" added={len(set(ia_c)-set(ib_c))} dropped={len(set(ib_c)-set(ia_c))}")
for name in sorted(set(ib_c) - set(ia_c)):
    print(f"    DROPPED constraint {name}")
    problems.append(f"constraint disappeared: {name}")
for name in ("ix_users_username", "ix_users_email"):
    got = rows(ca, "SELECT i.indisunique AS u FROM pg_index i"
                   " JOIN pg_class c ON c.oid=i.indexrelid"
                   " JOIN pg_namespace n ON n.oid=c.relnamespace"
                   " WHERE c.relname=%s AND n.nspname='public'", (name,))
    unique = bool(got and got[0]["u"])
    print(f"  catalog indisunique {name}: {unique if got else 'INDEX MISSING'}")
    if not got or not unique:
        problems.append(f"{name} is not a UNIQUE index in pg_index")
for col in ("username", "email"):
    groups = rows(ca, f"SELECT {col} AS v, count(*) AS n FROM users GROUP BY {col}"
                     " HAVING count(*) > 1")
    print(f"  duplicate {col} groups after migration: {groups or 'NONE'}")

after.close(); before.close()
print()
print("VERDICT:", "MIGRATION TOUCHED ONLY THE REVIEWED 120 ROWS" if not problems
      else f"UNEXPECTED CHANGES: {problems}")
sys.exit(0 if not problems else 1)
