"""BE-028 §8: characterise the duplicate groups (read-only)."""
from sqlalchemy import create_engine, text

TARGETS = {
    "pofa_test": "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test",
    "pofa_dev": "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev",
}

GROUPS = """
SELECT username, email, count(*) AS n, min(created_at) AS first_seen,
       max(created_at) AS last_seen
FROM users GROUP BY username, email HAVING count(*) > 1 ORDER BY n DESC
"""

DETAIL = """
SELECT id, username, email, identity_provider, status, is_active, created_at,
       display_name, external_subject
FROM users WHERE username = :u ORDER BY created_at
"""

# every table with an FK into users, and how many rows point at the duplicate ids
FK_REFS = """
SELECT tc.table_name, kcu.column_name, cc.constraint_name,
       rc.confdeltype
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
JOIN information_schema.constraint_column_usage cc
  ON cc.constraint_name = tc.constraint_name AND cc.table_schema = tc.table_schema
JOIN pg_constraint rc ON rc.conname = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND cc.table_name = 'users'
ORDER BY tc.table_name
"""

for name, url in TARGETS.items():
    e = create_engine(url)
    print("=" * 78)
    print(f"DATABASE {name}")
    with e.connect() as c:
        groups = c.execute(text(GROUPS)).mappings().all()
        for g in groups:
            print(f"\ngroup username={g['username']!r} email={g['email']!r} n={g['n']} "
                  f"first={g['first_seen']} last={g['last_seen']}")
        for g in groups:
            rows = c.execute(text(DETAIL), {"u": g["username"]}).mappings().all()
            ids = [r["id"] for r in rows]
            print(f"\n-- members of {g['username']!r} ({len(rows)}) --")
            for r in rows:
                print(f"   {r['id']} prov={r['identity_provider']} status={r['status']} "
                      f"active={r['is_active']} created={r['created_at']} "
                      f"display={r['display_name']!r} ext_subj={r['external_subject']!r}")
            print(f"\n-- FK references to these {len(ids)} ids --")
            fks = c.execute(text(FK_REFS)).mappings().all()
            total_refs = 0
            for fk in fks:
                tbl, col = fk["table_name"], fk["column_name"]
                q = text(f"SELECT count(*) FROM {tbl} WHERE {col} = ANY(:ids)")
                n = c.execute(q, {"ids": ids}).scalar()
                if n:
                    total_refs += n
                    print(f"   {tbl}.{col}  {n} rows  (on delete={fk['confdeltype']})")
            print(f"   TOTAL referencing rows: {total_refs}")
            owned = c.execute(
                text("SELECT count(*) FROM projects WHERE owner_id = ANY(:ids)"),
                {"ids": ids},
            ).scalar()
            print(f"   projects owned by the group: {owned}")
    e.dispose()
    print()
