"""BE-037A-D3 preflight: which identity can reach pofa_test, read-only.

Prints no credential material -- only the username and a couple of counts.
"""
import os
import re

from sqlalchemy import create_engine, text


def load_env(path):
    values = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


env = load_env("D:/CODING/Projects/Proof-Of-Action-Final/.env")
base = env.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
if not base:
    raise SystemExit("no DATABASE_URL available")

swap_url = re.sub(r"/[^/?]*$", "/pofa_test", base)

for label, url in (("env_identity", swap_url),):
    engine = create_engine(url)
    with engine.connect() as conn:
        user = conn.execute(text("SELECT current_user")).scalar()
        rev = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all()
        tables = conn.execute(
            text("SELECT count(*) FROM information_schema.tables "
                 "WHERE table_schema='public'")
        ).scalar()
        ledger = conn.execute(text("SELECT count(*) FROM audit_ledger_events")).scalar()
    print(f"{label}: user={user} revs={rev} tables={tables} ledger={ledger}")
    engine.dispose()
