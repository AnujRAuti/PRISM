"""BE-029 Phase 0: child rows under the residue projects (read-only)."""
import psycopg2
from psycopg2.extras import RealDictCursor

URLS = {"pofa_test": "postgresql://postgres:postgres@localhost:5432/pofa_test",
        "pofa_dev": "postgresql://postgres:postgres@localhost:5432/pofa_dev"}
FK = """
SELECT tc.constraint_name, kcu.table_name AS t, kcu.column_name AS c, rc.delete_rule,
       (SELECT count(*) FROM information_schema.constraint_column_usage ccu
         WHERE ccu.constraint_name = tc.constraint_name AND ccu.table_name = 'projects') AS u
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
"""
for label, url in URLS.items():
    print(f"\n================ {label} ================")
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM projects WHERE name = 'testproj'")
        pids = [r["id"] for r in cur.fetchall()]
        print("residue projects:", len(pids))
        cur.execute(FK)
        rows = [r for r in cur.fetchall() if r["u"]]
        grand = 0
        for r in rows:
            cur.execute(f'SELECT count(*) AS c FROM "{r["t"]}" WHERE "{r["c"]}" = ANY(%s::uuid[])',
                        (pids,))
            c = cur.fetchone()["c"]
            grand += c
            if c:
                print(f'    {r["t"]}.{r["c"]:<18} on_delete={r["delete_rule"]:<10} children={c}')
        print("    (FK columns with 0 children under residue projects: "
              f"{sum(1 for r in rows)} checked)")
        print("    TOTAL child rows under residue projects:", grand)
    conn.close()
