"""D2 closure proof: bootstrap a fresh disposable database and measure its catalogue.

Answers the exact question D2 raised -- does ``alembic upgrade head``, the one
documented bootstrap step, now produce a database that can authorize? -- on a
database this script owns and drops. Nothing here touches pofa_dev or pofa_test.

Steps: create -> extensions -> upgrade head -> measure -> downgrade -1 -> upgrade
head again (the seed must re-run as a no-op, and the data-only downgrade must not
destroy baseline configuration) -> measure -> drop.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import psycopg2

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
PYTHON = REPO / "backend" / ".venv312_repro" / "Scripts" / "python.exe"
COMPOSE = REPO / "docker-compose.yml"
FRESH = "be039d2_fresh"
HEAD = "u1v2w3x4y031"
PREVIOUS = "t0u1v2w3x030"

sys.path.insert(0, str(REPO))
from backend.db.models import (  # noqa: E402  (the constants are the expectation)
    AUTH_PERMISSIONS,
    AUTH_ROLE_PERMISSIONS,
    AUTH_ROLES,
)


def _resolve(raw: str) -> str:
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*):?-([^}]*)\}", raw.strip())
    if not match:
        return raw.strip().strip("'\"")
    return match.group(2) or match.group(1)


def owner() -> tuple[str, str]:
    text = COMPOSE.read_text(encoding="utf-8")
    values = {}
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD"):
        match = re.search(rf"^\s*{key}:\s*(.+)$", text, re.MULTILINE)
        if not match:
            raise SystemExit(f"{key} not found in {COMPOSE}")
        values[key] = _resolve(match.group(1))
    return values["POSTGRES_USER"], values["POSTGRES_PASSWORD"]


def connect(user: str, password: str, database: str):
    return psycopg2.connect(
        host="localhost", port=5432, user=user, password=password, dbname=database
    )


def measure(connection) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        name = cursor.fetchone()[0]
        cursor.execute("SELECT version_num FROM alembic_version")
        revision = cursor.fetchone()[0]
        counts = {}
        for table in ("roles", "permissions", "role_permissions"):
            cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 (fixed names)
            counts[table] = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM role_permissions rp "
                       "JOIN roles r ON r.id = rp.role_id "
                       "JOIN permissions p ON p.id = rp.permission_id")
        joined = cursor.fetchone()[0]
        cursor.execute(
            "SELECT p.name FROM permissions p "
            "EXCEPT SELECT name FROM (VALUES "
            + ", ".join(f"('{name}')" for name in AUTH_PERMISSIONS)
            + ") AS expected(name)"
        )
        extra_permissions = sorted(row[0] for row in cursor.fetchall())
    return {
        "database": name,
        "revision": revision,
        "counts": counts,
        "joined_grants": joined,
        "permissions_not_in_constants": extra_permissions,
    }


def expected() -> dict:
    return {
        "roles": len(AUTH_ROLES),
        "permissions": len(AUTH_PERMISSIONS),
        "role_permissions": sum(len(v) for v in AUTH_ROLE_PERMISSIONS.values()),
    }


def alembic(user: str, password: str, *arguments: str) -> int:
    import os

    environment = os.environ.copy()
    environment["DATABASE_URL"] = (
        f"postgresql+psycopg2://{user}:{password}@localhost:5432/{FRESH}"
    )
    return subprocess.call(
        [str(PYTHON), "-m", "alembic", *arguments],
        cwd=str(REPO),
        env=environment,
    )


def main() -> int:
    user, password = owner()
    want = expected()
    print(f"expected from constants: {want}")

    admin = connect(user, password, "postgres")
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(f'DROP DATABASE IF EXISTS "{FRESH}" WITH (FORCE)')
        cursor.execute(f'CREATE DATABASE "{FRESH}"')
    admin.close()

    fresh = connect(user, password, FRESH)
    fresh.autocommit = True
    with fresh.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    fresh.autocommit = False

    print("after CREATE DATABASE + extensions, before alembic:")
    with fresh.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM information_schema.tables "
                       "WHERE table_schema = 'public'")
        print(f"  public tables: {cursor.fetchone()[0]}")

    rc = alembic(user, password, "upgrade", "head")
    print(f"alembic upgrade head rc={rc}")
    first = measure(fresh)
    print(f"  after first upgrade: {first}")

    fresh.rollback()
    fresh.close()
    fresh = connect(user, password, FRESH)

    rc = alembic(user, password, "downgrade", "-1")
    print(f"alembic downgrade -1 (to {PREVIOUS}) rc={rc}")
    rc = alembic(user, password, "upgrade", "head")
    print(f"alembic upgrade head again rc={rc}")
    second = measure(fresh)
    print(f"  after re-seed: {second}")

    verdict = (
        rc == 0
        and first["revision"] == HEAD
        and first["counts"] == want
        and first["joined_grants"] == want["role_permissions"]
        and not first["permissions_not_in_constants"]
        and second["counts"] == want
    )
    print(f"D2 FRESH-BOOTSTRAP VERDICT: {'PASS' if verdict else 'FAIL'}")

    fresh.close()
    admin = connect(user, password, "postgres")
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(f'DROP DATABASE IF EXISTS "{FRESH}" WITH (FORCE)')
    admin.close()
    print(f"dropped {FRESH}")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
