"""BE-029 control clone: CREATE DATABASE <target> TEMPLATE pofa_dev.

Usage: python clone_db.py <target-db-name>

Used to build a pre-BE-029 control database so the six audit-chain integration
failures observed on the head clone can be attributed to a cause instead of
assumed. Aborts if anything is connected to the template, because PostgreSQL
refuses a TEMPLATE copy with active connections.
"""
import sys

import psycopg2
from psycopg2 import extras

ADMIN = "postgresql://postgres:postgres@localhost:5432/postgres"
SOURCE = "pofa_dev"
TARGET = sys.argv[1]

conn = psycopg2.connect(ADMIN)
conn.autocommit = True
with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
    cur.execute(
        "SELECT count(*) AS n, coalesce(string_agg(application_name, ','), '') AS who "
        "FROM pg_stat_activity WHERE datname = %s", (SOURCE,))
    live = cur.fetchone()
    if live["n"]:
        sys.exit(f"refusing: {live['n']} connection(s) to {SOURCE} [{live['who']}]")
    cur.execute("SELECT count(*) AS n FROM pg_database WHERE datname = %s", (TARGET,))
    if cur.fetchone()["n"]:
        cur.execute(f'DROP DATABASE "{TARGET}" WITH (FORCE)')
        print(f"dropped existing {TARGET}")
    cur.execute(f'CREATE DATABASE "{TARGET}" TEMPLATE "{SOURCE}"')
    print(f"created {TARGET} as a template copy of {SOURCE}")
conn.close()
