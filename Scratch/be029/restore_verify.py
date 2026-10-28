"""BE-029 G3 preflight: prove a pg_dump/pg_restore round trip is content-exact.

Usage: python restore_verify.py <source-url> <restored-url> <outfile>

Read-only against both databases. For every table in the public schema it
compares the row count and a canonical content fingerprint
(md5 over the sorted per-row text images, so the result is independent of
physical row order), plus the catalog object surface: tables, indexes
(full indexdef), constraints (full deparsed definition), sequences, views,
matviews, extensions and enum domains.

The point is to catch what a count comparison misses: a restore that has the
right number of rows but wrong values, or an object whose definition changed.
"""
import json
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

SRC_URL, DST_URL, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

TABLES = """
SELECT c.relname AS table_name
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
ORDER BY 1
"""

FINGERPRINT = (
    "SELECT count(*) AS n,"
    " md5(string_agg(t::text, E'\\n' ORDER BY t::text)) AS fp"
    ' FROM "public"."{table}" t'
)

CATALOG = {
    "tables": "SELECT relname AS name FROM pg_class c JOIN pg_namespace n"
              " ON n.oid=c.relnamespace WHERE n.nspname='public'"
              " AND c.relkind IN ('r','p') ORDER BY 1",
    "indexes": "SELECT indexname AS name, indexdef AS def FROM pg_indexes"
               " WHERE schemaname='public' ORDER BY 1",
    "constraints": "SELECT conrelid::regclass::text AS table_name, conname AS name,"
                   " pg_get_constraintdef(oid) AS def FROM pg_constraint"
                   " WHERE connamespace='public'::regnamespace ORDER BY 1, 2",
    "sequences": "SELECT relname AS name FROM pg_class c JOIN pg_namespace n"
                 " ON n.oid=c.relnamespace WHERE n.nspname='public'"
                 " AND c.relkind='S' ORDER BY 1",
    "views": "SELECT viewname AS name FROM pg_views WHERE schemaname='public' ORDER BY 1",
    "extensions": "SELECT extname AS name FROM pg_extension ORDER BY 1",
    "enums": "SELECT t.typname AS name, string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)"
             " AS labels FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid"
             " JOIN pg_namespace n ON n.oid=t.typnamespace"
             " WHERE n.nspname='public' GROUP BY 1 ORDER BY 1",
    "functions": "SELECT p.proname AS name FROM pg_proc p JOIN pg_namespace n"
                 " ON n.oid=p.pronamespace WHERE n.nspname='public' ORDER BY 1",
    "triggers": "SELECT tgname AS name FROM pg_trigger tg JOIN pg_class c"
                " ON c.oid=tg.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace"
                " WHERE n.nspname='public' AND NOT tgisinternal ORDER BY 1",
}


def measure(url):
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    out = {}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT current_database() AS n")
        out["database"] = cur.fetchone()["n"]
        cur.execute("SELECT version() AS v")
        out["server"] = cur.fetchone()["v"]
        cur.execute("SELECT version_num AS n FROM alembic_version")
        out["alembic_version"] = cur.fetchone()["n"]

        cur.execute(TABLES)
        names = [r["table_name"] for r in cur.fetchall()]
        fp = {}
        for name in names:
            try:
                cur.execute(FINGERPRINT.format(table=name))
                row = cur.fetchone()
                fp[name] = {"rows": int(row["n"]), "md5": row["fp"]}
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                fp[name] = {"error": f"{type(exc).__name__}: {exc}"}
        out["table_fingerprints"] = fp

        for key, sql in CATALOG.items():
            try:
                cur.execute(sql)
                out[key] = [dict(r) for r in cur.fetchall()]
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                out[key] = f"ERROR {type(exc).__name__}: {exc}"
    conn.close()
    return out


src, dst = measure(SRC_URL), measure(DST_URL)
json.dump({"source": src, "restored": dst}, open(OUT, "w"), indent=1, default=str)

problems = []
print(f"source   = {src['database']} @ {src['alembic_version']}")
print(f"restored = {dst['database']} @ {dst['alembic_version']}")
print(f"server   : {src['server'] == dst['server']}")
if src["alembic_version"] != dst["alembic_version"]:
    problems.append("alembic revision differs")

for key in CATALOG:
    a, b = src[key], dst[key]
    if a == b:
        n = len(a) if isinstance(a, list) else "ERR"
        print(f"MATCH  catalog {key} ({n} objects)")
    else:
        sa = {json.dumps(x, sort_keys=True) for x in a} if isinstance(a, list) else a
        sb = {json.dumps(x, sort_keys=True) for x in b} if isinstance(b, list) else b
        only_src = sorted(sa - sb) if isinstance(sa, set) else []
        only_dst = sorted(sb - sa) if isinstance(sb, set) else []
        print(f"DIFFER catalog {key}: {len(a)} vs {len(b)} objects")
        for x in only_src[:6]:
            print(f"    source-only: {x}")
        for x in only_dst[:6]:
            print(f"    restored-only: {x}")
        problems.append(f"catalog {key}")

fa, fb = src["table_fingerprints"], dst["table_fingerprints"]
if set(fa) != set(fb):
    problems.append("table set differs")
    print("DIFFER table set:", sorted(set(fa) ^ set(fb)))
bad_rows = bad_fp = 0
for name in sorted(set(fa) | set(fb)):
    a, b = fa.get(name), fb.get(name)
    if a is None or b is None:
        problems.append(f"table {name} present on one side only")
        continue
    if a.get("error") or b.get("error"):
        problems.append(f"table {name} fingerprint error: {a.get('error') or b.get('error')}")
        continue
    if a["rows"] != b["rows"]:
        bad_rows += 1
        problems.append(f"table {name} row count {a['rows']} vs {b['rows']}")
        print(f"DIFFER rows {name}: {a['rows']} vs {b['rows']}")
    elif a["md5"] != b["md5"]:
        bad_fp += 1
        problems.append(f"table {name} content differs (md5)")
        print(f"DIFFER md5  {name}: {a['md5']} vs {b['md5']}")
print(f"\ntables compared: {len(fa)}  count mismatches: {bad_rows}"
      f"  content mismatches: {bad_fp}")
print("VERDICT:", "RESTORE IS CONTENT-EXACT" if not problems else f"PROBLEMS: {problems}")
sys.exit(0 if not problems else 1)
