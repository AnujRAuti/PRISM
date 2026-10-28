"""BE-029 Phase 0: exact reference surface of the duplicate user ids (read-only)."""
import psycopg2
from psycopg2.extras import RealDictCursor

URLS = {
    "pofa_test": "postgresql://postgres:postgres@localhost:5432/pofa_test",
    "pofa_dev": "postgresql://postgres:postgres@localhost:5432/pofa_dev",
}
DUP_IDS = """SELECT id FROM users WHERE email = 'test@example.com' AND username = 'testuser'"""

FK = """
SELECT tc.constraint_name, kcu.table_name AS t, kcu.column_name AS c, rc.delete_rule,
       (SELECT count(*) FROM information_schema.constraint_column_usage ccu
         WHERE ccu.constraint_name = tc.constraint_name AND ccu.table_name = 'users') AS u
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
"""

LEDGER = """
SELECT count(*) AS rows_touching,
       count(*) FILTER (WHERE actor_id IN (SELECT id FROM users
             WHERE email='test@example.com' AND username='testuser')) AS as_actor,
       count(*) FILTER (WHERE resource_type='users' AND resource_id IN (SELECT id FROM users
             WHERE email='test@example.com' AND username='testuser')) AS as_resource
FROM audit_ledger_events
"""

PROJECTS = """
SELECT p.name, count(*) AS c FROM projects p
WHERE p.owner_id IN (SELECT id FROM users WHERE email='test@example.com' AND username='testuser')
GROUP BY p.name ORDER BY c DESC LIMIT 8
"""

for label, url in URLS.items():
    print(f"\n================ {label} ================")
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(DUP_IDS)
        ids = [r["id"] for r in cur.fetchall()]
        print("duplicate ids:", len(ids))
        cur.execute(FK)
        print("\n-- references to the duplicate id set, per FK column --")
        total = 0
        for r in cur.fetchall():
            if not r["u"]:
                continue
            cur.execute(f'SELECT count(*) AS c FROM "{r["t"]}" WHERE "{r["c"]}" = ANY(%s::uuid[])',
                        (ids,))
            c = cur.fetchone()["c"]
            total += c
            flag = "  <== NON-ZERO" if c else ""
            print(f'    {r["t"]}.{r["c"]:<16} on_delete={r["delete_rule"]:<10} refs={c}{flag}')
        print("    TOTAL references held by duplicate ids:", total)
        print("\n-- projects owned by the duplicate set (name pattern) --")
        cur.execute(PROJECTS)
        for r in cur.fetchall():
            print("   ", r["name"], "x", r["c"])
        print("\n-- audit ledger contact with the duplicate set --")
        cur.execute(LEDGER)
        print("   ", cur.fetchone())
    conn.close()
