"""BE-029 Phase 0: data-quality / residue-shape probe (read-only)."""
import psycopg2
from psycopg2.extras import RealDictCursor

URLS = {"pofa_test": "postgresql://postgres:postgres@localhost:5432/pofa_test",
        "pofa_dev": "postgresql://postgres:postgres@localhost:5432/pofa_dev"}

CHECKS = [
    ("total users", "SELECT count(*) c FROM users"),
    ("username NULL/empty/whitespace", "SELECT count(*) c FROM users WHERE username IS NULL OR btrim(username)=''"),
    ("email NULL/empty/whitespace", "SELECT count(*) c FROM users WHERE email IS NULL OR btrim(email)=''"),
    ("username = testuser (exact residue)", "SELECT count(*) c FROM users WHERE username='testuser'"),
    ("username LIKE 'testuser-%%' (fixed-test pattern)", "SELECT count(*) c FROM users WHERE username LIKE 'testuser-%'"),
    ("email LIKE 'test-%%@example.com' (fixed-test pattern)", "SELECT count(*) c FROM users WHERE email LIKE 'test-%@example.com'"),
    ("projects named exactly 'testproj'", "SELECT count(*) c FROM projects WHERE name='testproj'"),
    ("projects named 'testproj-%%'", "SELECT count(*) c FROM projects WHERE name LIKE 'testproj-%'"),
    ("projects with name NULL/empty", "SELECT count(*) c FROM projects WHERE name IS NULL OR btrim(name)=''"),
    ("duplicate project names overall", "SELECT count(*) c FROM (SELECT name FROM projects GROUP BY name HAVING count(*)>1) t"),
    ("users with status<>'ACTIVE'", "SELECT count(*) c FROM users WHERE status <> 'ACTIVE'"),
    ("users is_active=false", "SELECT count(*) c FROM users WHERE NOT is_active"),
    ("distinct identity_provider", "SELECT string_agg(DISTINCT identity_provider, ',') c FROM users"),
    ("longest username", "SELECT max(length(username)) c FROM users"),
    ("longest email", "SELECT max(length(email)) c FROM users"),
]

for label, url in URLS.items():
    print(f"\n================ {label} ================")
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for title, sql in CHECKS:
            cur.execute(sql)
            print(f"    {title:52} = {cur.fetchone()['c']}")
        # the exact set a merge would touch: non-oldest members of the duplicate group
        cur.execute("""
            SELECT count(*) c FROM (
              SELECT id, row_number() OVER (PARTITION BY email, username
                       ORDER BY created_at, id) rn
              FROM users) t WHERE t.rn > 1
        """)
        print(f"    {'rows retire-oldest-wins rule would touch':52} = {cur.fetchone()['c']}")
    conn.close()
