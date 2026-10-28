"""Phase 3: build a disposable reversibility database from the migrated pofa_dev.

Usage: python clone_from_dev.py <new-db-name>

Two refusals, both deliberate:
* the target must not already exist (this never overwrites a database), and
* nothing may be connected to the template, because CREATE DATABASE ... TEMPLATE
  takes an exclusive lock on the source -- which is live pofa_dev.
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
    cur.execute("SELECT count(*) AS n FROM pg_database WHERE datname = %s", (TARGET,))
    if cur.fetchone()["n"]:
        sys.exit(f"refusing: database {TARGET} already exists (never overwrite)")
    cur.execute(
        "SELECT count(*) AS n, coalesce(string_agg(application_name, ','), '') AS who "
        "FROM pg_stat_activity WHERE datname = %s", (SOURCE,))
    live = cur.fetchone()
    if live["n"]:
        sys.exit(f"refusing: {live['n']} connection(s) to {SOURCE} [{live['who']}]")
    cur.execute(f'CREATE DATABASE "{TARGET}" WITH TEMPLATE {SOURCE} OWNER postgres')
print(f"created {TARGET} as a template copy of {SOURCE}")
