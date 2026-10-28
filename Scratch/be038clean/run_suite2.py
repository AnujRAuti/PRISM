"""Arm the suite against pofa_test with the local development owner identity.

The first attempt here derived TEST_DATABASE_URL from the repo .env
DATABASE_URL, but that URL is the *runtime* role since the BE-035 cutover, and
the runtime role carries no grants on pofa_test -- so the suite died with
``permission denied for table audit_ledger_events``. That is an arming mistake
in this harness, not a repository defect.

pofa_test has always been driven as the compose bootstrap owner. The credentials
are read out of docker-compose.yml at run time so no secret is ever written into
this file or printed; only the resolved role name and database name appear.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
COMPOSE = REPO / "docker-compose.yml"


def _resolve(raw: str) -> str:
    """Return the effective value of a compose scalar, resolving ${VAR:-default}."""
    match = re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?-?([^}]*)\}", raw)
    if not match:
        return raw
    default = match.group(1)
    return default or raw


def owner_credentials() -> tuple[str, str]:
    found = {"POSTGRES_USER": "", "POSTGRES_PASSWORD": ""}
    for line in COMPOSE.read_text(encoding="utf-8").splitlines():
        match = re.match(
            r"\s*(?:-\s*)?(POSTGRES_USER|POSTGRES_PASSWORD)\s*[=:]\s*(.+?)\s*$", line
        )
        if not match:
            continue
        value = match.group(2).strip().strip('"').strip("'")
        found[match.group(1)] = _resolve(value)
    user, password = found["POSTGRES_USER"], found["POSTGRES_PASSWORD"]
    if not user or not password:
        raise SystemExit("could not read the compose bootstrap owner credentials")
    return user, password


def env_file_values() -> dict[str, str]:
    values = {}
    for line in (REPO / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip('"').strip("'")
    return values


def owner_test_url(port: str = "5432") -> str:
    user, password = owner_credentials()
    return f"postgresql+psycopg2://{user}:{password}@localhost:{port}/pofa_test"


def arm() -> None:
    os.chdir(REPO)
    sys.path.insert(0, str(REPO))
    values = env_file_values()
    if not values.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not present in .env")
    os.environ["DATABASE_URL"] = values["DATABASE_URL"]
    for key in ("REDIS_URL", "JWT_SECRET", "S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        if key in values:
            os.environ[key] = values[key]
    os.environ["TEST_DATABASE_URL"] = owner_test_url()


def describe_target() -> None:
    import psycopg2

    user, password = owner_credentials()
    with psycopg2.connect(
        host="localhost", port=5432, user=user, password=password, dbname="pofa_test"
    ) as conn:
        cur = conn.cursor()
        cur.execute("SELECT current_user, current_database(), version()")
        role, dbname, server = cur.fetchone()
    print(f"armed as role={role} database={dbname} server={server.split(',')[0]}")


if __name__ == "__main__":
    arm()
    describe_target()
    mode = sys.argv[1] if len(sys.argv) > 1 else "tests"
    import pytest

    args = ["-q", "--no-header", mode]
    if mode != "tests":
        args.insert(2, "--tb=short")
    raise SystemExit(pytest.main(args))
