"""Phase 4/5: read-only foreign-key integrity sweep of one database.

Usage: python rb_fk_check.py <postgres-url>

Walks every foreign key in the public schema (column names taken from the
catalog, not parsed out of constraint text) and counts child rows whose parent is
missing. Used to show that restoring archived rows -- and dropping the archive
table -- leaves no dangling references anywhere in the database, not just in the
three tables the migration touches.
"""
import sys

import psycopg2
from psycopg2 import extras

conn = psycopg2.connect(sys.argv[1])
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=extras.RealDictCursor)
cur.execute("SELECT current_database() AS d")
print(f"database={cur.fetchone()['d']}")

cur.execute(
    "SELECT con.conname, child.relname AS child_table, parent.relname AS parent_table,"
    " ARRAY(SELECT a.attname FROM pg_attribute a"
    "         WHERE a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)"
    "         ORDER BY array_position(con.conkey, a.attnum)) AS cols,"
    " ARRAY(SELECT a.attname FROM pg_attribute a"
    "         WHERE a.attrelid = con.confrelid AND a.attnum = ANY(con.confkey)"
    "         ORDER BY array_position(con.confkey, a.attnum)) AS pcols"
    " FROM pg_constraint con"
    " JOIN pg_class child ON child.oid = con.conrelid"
    " JOIN pg_class parent ON parent.oid = con.confrelid"
    " JOIN pg_namespace n ON n.oid = child.relnamespace"
    " WHERE con.contype = 'f' AND n.nspname = 'public'"
    " ORDER BY child.relname, con.conname")
fks = cur.fetchall()

bad = 0
for fk in fks:
    on = " AND ".join(f'p."{pc}" = c."{cc}"'
                      for cc, pc in zip(fk["cols"], fk["pcols"]))
    cur.execute(f'SELECT count(*) AS n FROM "{fk["child_table"]}" c'
                f' LEFT JOIN "{fk["parent_table"]}" p ON {on}'
                f' WHERE p."{fk["pcols"][0]}" IS NULL AND c."{fk["cols"][0]}" IS NOT NULL')
    orphans = cur.fetchone()["n"]
    if orphans:
        bad += 1
        print(f"  ORPHANS {fk['child_table']}.{fk['conname']}"
              f" -> {fk['parent_table']}: {orphans}")
print(f"\nforeign keys checked: {len(fks)} | with dangling child rows: {bad}")
print("VERDICT: " + ("FAIL" if bad else "no foreign key in the database has an orphan row"))
conn.close()
sys.exit(1 if bad else 0)
