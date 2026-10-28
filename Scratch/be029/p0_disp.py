import psycopg2
from psycopg2.extras import RealDictCursor
for label, url in {"pofa_test": "postgresql://postgres:postgres@localhost:5432/pofa_test",
                   "pofa_dev": "postgresql://postgres:postgres@localhost:5432/pofa_dev"}.items():
    conn = psycopg2.connect(url); conn.set_session(readonly=True, autocommit=True)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT display_name IS NULL AS dn_null, count(*) c FROM users
                       WHERE username='testuser' AND email='test@example.com' GROUP BY 1""")
        print(label, "residue display_name:", [dict(r) for r in cur.fetchall()])
        cur.execute("""SELECT count(*) c FROM users WHERE display_name IS NULL""")
        print(label, "all users display_name NULL:", cur.fetchone()["c"])
    conn.close()
