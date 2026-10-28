"""Arm this machine's protected test database for one command, in-process.

Two entry points, because the repo has two different obligations:

* ``alembic <args>``  -- sets DATABASE_URL to the Compose bootstrap owner DSN for
  pofa_test. Outside pytest nothing republishes TEST_DATABASE_URL, and since the
  BE-035 cutover the repo's own .env carries poa_runtime, which holds no grants
  there; a manual alembic run would otherwise target the wrong database or fail.
* ``pytest <args>``   -- sets TEST_DATABASE_URL to that same DSN, which
  tests/conftest.py turns into the armed, server-confirmed test target.

Credentials are read from docker-compose.yml, used in-process only, and never
printed: this script's output carries no DSN and no password.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
PYTHON = REPO / "backend" / ".venv312_repro" / "Scripts" / "python.exe"
COMPOSE = REPO / "docker-compose.yml"
TEST_DATABASE = "pofa_test"


def _resolve(raw: str) -> str:
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*):?-([^}]*)\}", raw.strip())
    if not match:
        return raw.strip().strip("'\"")
    return match.group(2) or match.group(1)


def owner_dsn() -> str:
    text = COMPOSE.read_text(encoding="utf-8")
    values = {}
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD"):
        match = re.search(rf"^\s*{key}:\s*(.+)$", text, re.MULTILINE)
        if not match:
            raise SystemExit(f"{key} not found in {COMPOSE}")
        values[key] = _resolve(match.group(1))
    return (
        f"postgresql+psycopg2://{values['POSTGRES_USER']}:"
        f"{values['POSTGRES_PASSWORD']}@localhost:5432/{TEST_DATABASE}"
    )


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    kind, rest = argv[0], argv[1:]
    environment = os.environ.copy()
    if kind == "alembic":
        # .env carries the poa_runtime credential since the BE-035 cutover, and
        # that identity holds no grant on alembic_version, so a migration run
        # inherits a credential that cannot migrate.
        environment["DATABASE_URL"] = owner_dsn()
        rest = ["-m", "alembic", *rest]
    elif kind == "pytest":
        environment["TEST_DATABASE_URL"] = owner_dsn()
        rest = ["-m", "pytest", *rest]
    else:
        raise SystemExit(f"unknown kind: {kind!r} (expected 'alembic' or 'pytest')")
    return subprocess.call([str(PYTHON), *rest], cwd=str(REPO), env=environment)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
