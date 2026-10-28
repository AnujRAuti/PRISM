"""Arm the disposable infrastructure the full suite's skipped obligations require.

Measured, not assumed: the last full-suite run reported `1 failed, 919 passed,
14 skipped`. Thirteen of those fourteen skips are obligations that only execute
when the run supplies its own infrastructure through an environment variable --
and one of them (`test_verification_context_accepts_this_runs_disposable_database`)
FAILED precisely because the suite ran on `pofa_test`, a name the safety guard
classifies as protected. A green-ish run with the opt-in checks skipped is not
the required measurement.

Four obligations, four arms:

  TEST_DATABASE_URL                    this run's disposable database, migrated
                                       to head. Never pofa_dev / pofa_test.
  POA_DISPOSABLE_OWNER_DATABASE_URL    a second disposable database, migrated to
                                       head; the ledger identity matrix creates
                                       and drops per-run roles there.
  POA_PROTECTED_NAME_PROBE_DATABASE_URL a database that *answers* with the name
                                       `pofa_test`, on a separate disposable
                                       cluster, so the protected-name refusal can
                                       be proven over a real connection.
  POA_DISPOSABLE_REDIS_URL/_CONTAINER  a disposable Redis the outage tests may
                                       pause and restart.
  POA_DISPOSABLE_MINIO_CONTAINER       a disposable MinIO the storage test may
                                       restart, published on the port the run's
                                       S3_ENDPOINT reads.

Nothing here touches pofa_db's long-lived databases, pofa_redis or pofa_minio;
every name created is prefixed `poa_disp_`. Generated passwords are written to a
0600 state file and never printed.

usage:  python armfull.py up | suite [pytest args] | down
"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
PYTHON = REPO / "backend" / ".venv312_repro" / "Scripts" / "python.exe"
STATE = Path(__file__).with_name("armfull_state.json")

PG_IMAGE = "garapadev/postgres-postgis-pgvector:15-stable"
SUITE_DB = "poa_disp_suite"
OWNER_DB = "poa_disp_owner"
PROBE_DB = "pofa_test"          # deliberately protected-named, on a disposable cluster
PROBE_CONT = "poa_disp_pg"
REDIS_CONT = "poa_disp_redis"
MINIO_CONT = "poa_disp_minio"
PROTECTED_NAMES = {"pofa_dev", "pofa_test"}

PG_PORT, PROBE_PORT, REDIS_PORT, MINIO_PORT = 5432, 5433, 16379, 9100
EVIDENCE_BUCKET, QUARANTINE_BUCKET = "pofa-evidence", "pofa-quarantine"


def compose_value(key: str, default: str) -> str:
    text = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    match = re.search(rf"^\s*{key}:\s*\$\{{{key}:-([^}}]*)\}}", text, re.MULTILINE)
    return match.group(1) if match else default


def admin_dsn(database: str) -> str:
    user = compose_value("POSTGRES_USER", "postgres")
    pw = compose_value("POSTGRES_PASSWORD", "postgres")
    return f"postgresql+psycopg2://{user}:{pw}@localhost:{PG_PORT}/{database}"


def sh(args, *, stdin=None, cwd=REPO, env=None, quiet=False):
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(cwd),
                          input=stdin, env=env)
    if proc.returncode and not quiet:
        raise SystemExit(f"{' '.join(args[:4])} -> rc={proc.returncode}\n"
                         f"{(proc.stderr or proc.stdout).strip()[:400]}")
    return proc


def psql(database: str, statement: str) -> str:
    user = compose_value("POSTGRES_USER", "postgres")
    return sh(["docker", "exec", "pofa_db", "psql", "-U", user, "-d", database,
               "-tAc", statement]).stdout.strip()


def container_running(name: str) -> bool:
    return sh(["docker", "inspect", "-f", "{{.State.Running}}", name],
              quiet=True).stdout.strip() == "true"


def up() -> dict:
    if SUITE_DB in PROTECTED_NAMES or OWNER_DB in PROTECTED_NAMES:
        raise SystemExit("refusing: disposable name collides with a protected database")
    admin = compose_value("POSTGRES_USER", "postgres")

    # ---- disposable databases on the existing cluster -------------------
    for database in (SUITE_DB, OWNER_DB):
        exists = psql("postgres", f"select 1 from pg_database where datname='{database}'")
        if exists != "1":
            sh(["docker", "exec", "pofa_db", "createdb", "-U", admin, database])
        print(f"database {database:<16}: ready")
        proc = sh([str(PYTHON), "-m", "alembic", "upgrade", "head"],
                  env={**subprocess.os.environ, "DATABASE_URL": admin_dsn(database)})
        if proc.returncode:
            raise SystemExit(f"alembic upgrade head on {database} failed:\n"
                             + proc.stderr.strip()[-500:])
        rev = psql(database, "select version_num from alembic_version")
        tables = psql(database, "select count(*) from information_schema.tables "
                                "where table_schema='public'")
        print(f"  alembic {rev} | {tables} tables")

    # ---- disposable Redis ------------------------------------------------
    if not container_running(REDIS_CONT):
        sh(["docker", "run", "-d", "--name", REDIS_CONT, "-p", f"{REDIS_PORT}:6379",
            "redis:7-alpine"])
    print(f"redis  {REDIS_CONT}: redis://localhost:{REDIS_PORT}/0")

    # ---- disposable MinIO (own volume, own port, own keys) --------------
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    minio_user = "poa_disp"
    minio_pw = state.get("minio_password") or secrets.token_urlsafe(18)
    probe_pw = state.get("probe_password") or secrets.token_urlsafe(18)
    if not container_running(MINIO_CONT):
        sh(["docker", "run", "-d", "--name", MINIO_CONT,
            "-p", f"{MINIO_PORT}:9000", "-p", f"{MINIO_PORT + 1}:9001",
            "-e", f"MINIO_ROOT_USER={minio_user}", "-e", f"MINIO_ROOT_PASSWORD={minio_pw}",
            "-v", "poa_disp_minio_data:/data", "quay.io/minio/minio:latest",
            "server", "/data"])
    wait_for_port(MINIO_PORT)
    ensure_buckets(minio_user, minio_pw)
    print(f"minio  {MINIO_CONT}: http://localhost:{MINIO_PORT} "
          f"(buckets {EVIDENCE_BUCKET}, {QUARANTINE_BUCKET} verified)")

    # ---- disposable cluster hosting a protected-NAMED database -----------
    if not container_running(PROBE_CONT):
        sh(["docker", "run", "-d", "--name", PROBE_CONT, "-p", f"{PROBE_PORT}:5432",
            "-e", "POSTGRES_USER=poa_probe", "-e", f"POSTGRES_PASSWORD={probe_pw}",
            "-e", f"POSTGRES_DB={PROBE_DB}", PG_IMAGE])
        time.sleep(6)
    answered = sh(["docker", "exec", PROBE_CONT, "psql", "-U", "poa_probe", "-d", PROBE_DB,
                   "-tAc", "select current_database()"]).stdout.strip()
    print(f"probe  {PROBE_CONT}: server reports {answered!r} on a disposable cluster")

    state.update({"minio_password": minio_pw, "probe_password": probe_pw,
                  "minio_user": minio_user})
    STATE.write_text(json.dumps(state))
    os.chmod(STATE, 0o600)
    print(f"\narm state written to {STATE.name} (never printed)")
    return state


def ensure_buckets(minio_user: str, minio_pw: str) -> None:
    """Create the two buckets and then *read back* that they exist.

    The first armed run silently skipped this: the command was issued once against
    a MinIO still coming up, its error was swallowed, and every storage test then
    failed against a server with no buckets. Verification is the listing, not the
    `mc mb` exit code.
    """
    shell = (f"mc alias set local http://localhost:9000 {minio_user} {minio_pw} "
             f">/dev/null 2>&1 || exit 11; "
             f"mc mb -p local/{EVIDENCE_BUCKET} local/{QUARANTINE_BUCKET} >/dev/null 2>&1; "
             f"mc ls local")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        listed = sh(["docker", "exec", MINIO_CONT, "sh", "-c", shell], quiet=True)
        names = {line.split()[-1].rstrip("/") for line in listed.stdout.splitlines() if line}
        if {EVIDENCE_BUCKET, QUARANTINE_BUCKET} <= names:
            return
        time.sleep(3)
    raise SystemExit(f"disposable MinIO never exposed {EVIDENCE_BUCKET} / "
                     f"{QUARANTINE_BUCKET}; arming is incomplete")


def wait_for_port(port: int, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(1.0)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(1.0)
    raise SystemExit(f"port {port} never opened")


def arm_env() -> dict:
    state = json.loads(STATE.read_text())
    probe = (f"postgresql+psycopg2://poa_probe:{state['probe_password']}"
             f"@localhost:{PROBE_PORT}/{PROBE_DB}")
    return {
        "TEST_DATABASE_URL": admin_dsn(SUITE_DB),
        "POA_DISPOSABLE_OWNER_DATABASE_URL": admin_dsn(OWNER_DB),
        "POA_PROTECTED_NAME_PROBE_DATABASE_URL": probe,
        "POA_DISPOSABLE_REDIS_URL": f"redis://localhost:{REDIS_PORT}/0",
        "POA_DISPOSABLE_REDIS_CONTAINER": REDIS_CONT,
        "POA_DISPOSABLE_MINIO_CONTAINER": MINIO_CONT,
        "S3_ENDPOINT": f"http://localhost:{MINIO_PORT}",
        "S3_ACCESS_KEY": state["minio_user"],
        "S3_SECRET_KEY": state["minio_password"],
    }


def suite(argv: list[str]) -> int:
    env = {**subprocess.os.environ, **arm_env()}
    args = [str(PYTHON), "-m", "pytest", *(argv or ["tests"]), "-q",
            "--no-header", "-rf"]
    proc = subprocess.Popen(args, cwd=str(REPO), env=env)
    return proc.wait()


def down() -> int:
    admin = compose_value("POSTGRES_USER", "postgres")
    for database in (SUITE_DB, OWNER_DB):
        sh(["docker", "exec", "pofa_db", "dropdb", "-U", admin, "--if-exists", database])
        print(f"dropped database {database}")
    for name in (PROBE_CONT, REDIS_CONT, MINIO_CONT):
        sh(["docker", "rm", "-f", name], quiet=True)
        print(f"removed container {name}")
    sh(["docker", "volume", "rm", "poa_disp_minio_data"], quiet=True)
    if STATE.exists():
        STATE.unlink()
    print("arm state removed")
    return 0


if __name__ == "__main__":
    if not sys.argv[1:]:
        raise SystemExit(__doc__)
    kind, rest = sys.argv[1], sys.argv[2:]
    if kind == "up":
        up()
    elif kind == "suite":
        sys.exit(suite(rest))
    elif kind == "down":
        down()
    else:
        raise SystemExit(f"unknown kind: {kind}")
