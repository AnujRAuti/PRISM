"""PRISM-5: capture the exact failure when the migration chain is run backwards.

The empty-database proof reported `downgrade base` returning rc=1 with all 73
tables still present, but it only kept the return code.  A rollback path that
does not work is a release finding, so this run keeps the full traceback.

Creates and drops only poa_prism5_dg.  No connection string is printed.
"""

from __future__ import annotations

import re
import subprocess
import sys

DB = "poa_prism5_dg"
CONTAINER = "pofa_db"
REPO = r"D:/CODING/Projects/Proof-Of-Action-Final"
PYTHON = f"{REPO}/backend/.venv312_repro/Scripts/python.exe"


def compose_default(key: str, fallback: str) -> str:
    text = open(f"{REPO}/docker-compose.yml", encoding="utf-8").read()
    match = re.search(rf"^\s*{key}:\s*\$\{{{key}:-([^}}]*)\}}", text, re.MULTILINE)
    return match.group(1) if match else fallback


USER = compose_default("POSTGRES_USER", "postgres")
PASSWORD = compose_default("POSTGRES_PASSWORD", "postgres")
DSN = f"postgresql+psycopg2://{USER}:{PASSWORD}@localhost:5432/{DB}"


def psql(database: str, statement: str) -> str:
    proc = subprocess.run(["docker", "exec", CONTAINER, "psql", "-U", USER,
                           "-d", database, "-tAc", statement],
                          cwd=REPO, capture_output=True, text=True)
    return proc.stdout.strip()


def alembic(*arguments: str) -> None:
    env = {**subprocess.os.environ, "DATABASE_URL": DSN}
    proc = subprocess.run([PYTHON, "-m", "alembic", *arguments], cwd=REPO,
                          capture_output=True, text=True, env=env)
    print(f"\n$ alembic {' '.join(arguments)}  -> rc={proc.returncode}")
    print((proc.stdout + proc.stderr)[-6000:])


if __name__ == "__main__":
    psql("postgres", f"drop database if exists {DB} with (force)")
    psql("postgres", f"create database {DB}")
    alembic("upgrade", "head")
    alembic("downgrade", "base")
    print("tables after downgrade:",
          psql(DB, "select count(*) from information_schema.tables "
                   "where table_schema='public' and table_type='BASE TABLE'"))
    alembic("current")
    psql("postgres", f"drop database if exists {DB} with (force)")
