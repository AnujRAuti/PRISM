"""BE-029 Phase 0: read-only facts about the users identity surface."""
import psycopg2
from psycopg2.extras import RealDictCursor

URLS = {
    "pofa_test": "postgresql://postgres:postgres@localhost:5432/pofa_test",
    "pofa_dev": "postgresql://postgres:postgres@localhost:5432/pofa_dev",
}

CONSTRAINTS = """
SELECT conname, pg_get_constraintdef(oid) AS def
FROM pg_constraint WHERE conrelid = 'public.users'::regclass ORDER BY conname
"""
INDEXES = """
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename = 'users' ORDER BY indexname
"""
NULLS = """
SELECT count(*) AS total,
       count(*) FILTER (WHERE external_subject IS NULL) AS null_subject,
       count(*) FILTER (WHERE external_subject = id::text) AS subject_eq_id,
       count(*) FILTER (WHERE external_subject IS NOT NULL
                          AND external_subject <> id::text) AS subject_other
FROM users
"""
GROUPS = """
SELECT email, username, count(*) AS members,
       min(created_at)::text AS earliest, max(created_at)::text AS latest,
       count(*) FILTER (WHERE external_subject IS NULL) AS nulls,
       count(*) FILTER (WHERE external_subject = id::text) AS eq_id,
       count(*) FILTER (WHERE identity_provider = 'local') AS local_rows,
       count(*) FILTER (WHERE status = 'ACTIVE') AS active,
       count(*) FILTER (WHERE is_active) AS is_active_true
FROM users GROUP BY email, username HAVING count(*) > 1 ORDER BY members DESC
"""
PER_GROUP = """
SELECT u.email, u.username, u.id::text AS id, u.created_at::text AS created_at,
       u.status, u.is_active,
       (u.external_subject IS NULL) AS subject_is_null,
       (u.external_subject = u.id::text) AS subject_eq_id,
       (SELECT count(*) FROM projects p WHERE p.owner_id = u.id) AS owned_projects,
       (SELECT count(*) FROM user_role_assignments a WHERE a.user_id = u.id) AS role_rows
FROM users u
WHERE u.email IN (SELECT email FROM users GROUP BY email HAVING count(*) > 1)
ORDER BY u.email, u.created_at
"""
SCALARS = [
    ("dup-by-email groups", "SELECT count(*) c FROM (SELECT email FROM users GROUP BY email HAVING count(*)>1) t"),
    ("dup-by-username groups", "SELECT count(*) c FROM (SELECT username FROM users GROUP BY username HAVING count(*)>1) t"),
    ("casefold dup email groups", "SELECT count(*) c FROM (SELECT lower(email) e FROM users GROUP BY lower(email) HAVING count(*)>1) t"),
    ("casefold dup username groups", "SELECT count(*) c FROM (SELECT lower(username) e FROM users GROUP BY lower(username) HAVING count(*)>1) t"),
    ("plus-tag dup email groups", "SELECT count(*) c FROM (SELECT split_part(email,'+',1) e FROM users GROUP BY split_part(email,'+',1) HAVING count(*)>1) t"),
    ("projects owner_id NULL", "SELECT count(*) c FROM projects WHERE owner_id IS NULL"),
    ("projects orphan owner", "SELECT count(*) c FROM projects p LEFT JOIN users u ON u.id=p.owner_id WHERE p.owner_id IS NOT NULL AND u.id IS NULL"),
]
ALL_FK = """
SELECT tc.constraint_name, kcu.table_name AS from_table, kcu.column_name, rc.delete_rule,
       (SELECT count(*) FROM information_schema.constraint_column_usage ccu
         WHERE ccu.constraint_name = tc.constraint_name AND ccu.table_name = 'users') AS points_at_users
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
ORDER BY from_table, tc.constraint_name
"""

for label, url in URLS.items():
    print(f"\n================ {label} ================")
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        print("\n-- users constraints --")
        cur.execute(CONSTRAINTS)
        for r in cur.fetchall():
            print("   ", r["conname"], "::", r["def"])
        print("\n-- users indexes --")
        cur.execute(INDEXES)
        for r in cur.fetchall():
            print("   ", r["indexname"], "::", r["indexdef"])
        print("\n-- external_subject shape --")
        cur.execute(NULLS)
        print("   ", cur.fetchone())
        print("\n-- duplicate (email,username) groups --")
        cur.execute(GROUPS)
        rows = cur.fetchall()
        print("   count:", len(rows))
        for r in rows:
            print("   ", dict(r))
        print("\n-- members of duplicate groups --")
        cur.execute(PER_GROUP)
        for r in cur.fetchall():
            print("   ", dict(r))
        print("\n-- scalars --")
        for title, sql in SCALARS:
            cur.execute(sql)
            print("   ", title, "=", cur.fetchone()["c"])
        print("\n-- FKs pointing at users(id) --")
        cur.execute(ALL_FK)
        fk = cur.fetchall()
        for r in fk:
            if not r["points_at_users"]:
                continue
            cur.execute(f'SELECT count(*) c FROM "{r["from_table"]}" '
                        f'WHERE "{r["column_name"]}" IS NOT NULL')
            n = cur.fetchone()["c"]
            print(f'    {r["from_table"]}.{r["column_name"]} '
                  f'({r["constraint_name"]}) on_delete={r["delete_rule"]} non_null_rows={n}')
    conn.close()
