"""Provision the least-privileged runtime role on this VM's database.

scripts/provision_runtime_roles.sql wants its password as the psql variable
:runtime_password, whose value must itself carry the SQL single quotes (that is
what its documented `-v runtime_password="'...'"` invocation produces). Passing
it that way keeps the repo script byte-for-byte untouched, including its
refuse-to-create-an-open-role guard.

The secret travels only as the contents of two 0600 files inside the container,
is never printed, and the files are removed on the way out.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path.home() / "proof-of-action"
ENV_PATH = REPO / ".env"
CONTAINER = "pofa_db"

RUNNER = """#!/bin/sh
set -e
PW=$(cat /tmp/.poa_pw)
exec psql -v ON_ERROR_STOP=1 -v runtime_password="'$PW'" \\
     -U {owner} -d {database} -f /tmp/provision.sql
"""


def env_value(key: str) -> str:
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"{key} missing from .env")


def run(args: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=True, text=True, cwd=REPO)
    if proc.returncode:
        raise SystemExit(f"{args[-1]} failed: {proc.stderr.strip()[:300]}")
    return proc


def write_into_container(path: str, content: str) -> None:
    host = Path("/tmp/.poa_stage")
    host.write_text(content)
    run(["docker", "cp", str(host), f"{CONTAINER}:{path}"])
    host.unlink()
    run(["docker", "exec", CONTAINER, "chmod", "600", path])


def main() -> int:
    database = env_value("POSTGRES_DB")
    owner = env_value("POSTGRES_USER")
    runtime_password = env_value("POA_RUNTIME_DB_PASSWORD")

    run(["docker", "cp", "scripts/provision_runtime_roles.sql",
         f"{CONTAINER}:/tmp/provision.sql"])
    write_into_container("/tmp/.poa_pw", runtime_password)
    write_into_container("/tmp/.poa_run.sh", RUNNER.format(owner=owner, database=database))

    out = run(["docker", "exec", CONTAINER, "sh", "/tmp/.poa_run.sh"])
    run(["docker", "exec", CONTAINER, "rm", "-f",
         "/tmp/.poa_pw", "/tmp/.poa_run.sh", "/tmp/provision.sql"])

    lines = [line for line in out.stdout.splitlines() if line.strip()]
    print("--- last lines of script output (self-check is the last) ---")
    print("\n".join(lines[-10:]))

    check = run(["docker", "exec", CONTAINER, "psql", "-U", owner, "-d", database, "-tAc",
                 "select rolname||' super='||rolsuper||' createrole='||rolcreaterole"
                 " from pg_roles where rolname in ('poa_runtime','poa_migrator') "
                 "order by rolname"])
    print("--- roles ---")
    print(check.stdout.strip() or "(none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
