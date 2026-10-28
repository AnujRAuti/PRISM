"""BE-029 Phase 0: last level -- are the residue evidence rows leaves? (read-only)"""
import psycopg2
from psycopg2.extras import RealDictCursor

URLS = {"pofa_test": "postgresql://postgres:postgres@localhost:5432/pofa_test",
        "pofa_dev": "postgresql://postgres:postgres@localhost:5432/pofa_dev"}
EV = """
SELECT e.id, e.filename, e.created_at::text
FROM evidence e WHERE e.project_id IN (SELECT id FROM projects WHERE name='testproj')
ORDER BY e.created_at LIMIT 3
"""
EV_COUNT = """
SELECT count(*) c, count(DISTINCT filename) files FROM evidence
WHERE project_id IN (SELECT id FROM projects WHERE name='testproj')
"""
FK = """
SELECT tc.constraint_name, kcu.table_name AS t, kcu.column_name AS c, rc.delete_rule,
       (SELECT count(*) FROM information_schema.constraint_column_usage ccu
         WHERE ccu.constraint_name = tc.constraint_name AND ccu.table_name = 'evidence') AS u
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
        cur.execute(EV_COUNT)
        print("    residue evidence rows:", cur.fetchone())
        cur.execute(EV)
        for r in cur.fetchall():
            print("    sample:", dict(r))
        cur.execute("SELECT id FROM evidence WHERE project_id IN "
                    "(SELECT id FROM projects WHERE name='testproj')")
        eids = [r["id"] for r in cur.fetchall()]
        cur.execute(FK)
        for r in cur.fetchall():
            if not r["u"]:
                continue
            cur.execute(f'SELECT count(*) AS c FROM "{r["t"]}" WHERE "{r["c"]}" = ANY(%s::uuid[])',
                        (eids,))
            c = cur.fetchone()["c"]
            if c:
                print(f'    {r["t"]}.{r["c"]:<20} on_delete={r["delete_rule"]:<10} children={c}')
        print("    (no lines above = residue evidence rows are leaves)")
    conn.close()
