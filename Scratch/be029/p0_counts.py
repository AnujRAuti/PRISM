import psycopg2
from psycopg2.extras import RealDictCursor
import psycopg2.errors  # noqa
TABLES = ["users", "projects", "evidence", "review_cases", "review_decisions",
          "audit_ledger_events", "user_role_assignments", "claims", "activities"]
for label, url in {"pofa_test": "postgresql://postgres:postgres@localhost:5432/pofa_test",
                   "pofa_dev": "postgresql://postgres:postgres@localhost:5432/pofa_dev"}.items():
    conn = psycopg2.connect(url); conn.set_session(readonly=True, autocommit=True)
    out = {}
    with conn.cursor() as cur:
        for t in TABLES:
            try:
                cur.execute(f'SELECT count(*) FROM "{t}"')
                out[t] = cur.fetchone()[0]
            except psycopg2.errors.UndefinedTable:
                conn.rollback(); out[t] = "no table"
            except Exception:
                conn.rollback(); out[t] = "err"
    print(label, out)
    conn.close()
