"""Phase A/D: read-only measurement of the users identity-key columns in one database.

Usage: python subject_probe.py <postgres-url>

Answers, from the data rather than from the docs: how many rows have a NULL
external_subject, how many hold the BE-016 backfill shape (subject == id::text),
how many hold the service shape (a uuid4 that is NOT their own id), which
identity_provider values actually exist, and whether the declared composite key
(provider, subject) currently discriminates anything at all.
"""
import sys

import psycopg2
from psycopg2 import extras

SQL = """
SELECT count(*) AS n_total,
       count(*) FILTER (WHERE external_subject IS NULL) AS n_null,
       count(*) FILTER (WHERE external_subject IS NOT NULL
                        AND external_subject = id::text) AS n_self_id,
       count(*) FILTER (WHERE external_subject IS NOT NULL
                        AND external_subject <> id::text) AS n_other,
       count(DISTINCT identity_provider) AS n_providers,
       count(DISTINCT external_subject) FILTER (WHERE external_subject IS NOT NULL)
           AS n_distinct_subject
FROM users
"""

DUPES = """
SELECT identity_provider, external_subject, count(*) AS n
FROM users
WHERE external_subject IS NOT NULL
GROUP BY identity_provider, external_subject
HAVING count(*) > 1
ORDER BY n DESC LIMIT 10
"""

PROVIDERS = """
SELECT identity_provider, count(*) AS n,
       count(*) FILTER (WHERE external_subject IS NULL) AS n_null_subject
FROM users GROUP BY identity_provider ORDER BY n DESC
"""

SHAPE = """
SELECT left(external_subject, 8) AS head, length(external_subject) AS len,
       count(*) AS n
FROM users
WHERE external_subject IS NOT NULL AND external_subject <> id::text
GROUP BY head, len ORDER BY n DESC LIMIT 10
"""

conn = psycopg2.connect(sys.argv[1])
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=extras.RealDictCursor)
cur.execute("SELECT current_database() AS d")
db = cur.fetchone()["d"]
print(f"=== {db} ===")
cur.execute(SQL)
print(" " + " | ".join(f"{k}={v}" for k, v in cur.fetchone().items()))
cur.execute(PROVIDERS)
for r in cur.fetchall():
    print(f" provider {r['identity_provider']!r}: rows={r['n']} "
          f"null_subject={r['n_null_subject']}")
cur.execute(DUPES)
dupe_rows = cur.fetchall()
print(f" (provider, subject) duplicate groups: {len(dupe_rows)}")
for r in dupe_rows:
    print(f"   {r['identity_provider']!r} / {r['external_subject']!r} -> {r['n']}")
cur.execute(SHAPE)
shape = cur.fetchall()
print(f" non-self-id subject shapes (top {len(shape)}):")
for r in shape:
    print(f"   head={r['head']!r} len={r['len']} n={r['n']}")
conn.close()
