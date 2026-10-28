"""Manage this VM deployment's .env without ever printing a secret value.

Modes:
  show   -- key names, and for connection strings only the non-secret parts.
  check  -- ask Postgres who we are over the unix socket, and whether the
            schema is still empty (so rotation cannot destroy anything).
  rotate -- mint fresh secrets, apply the owner password to the live cluster,
            prove the new password authenticates over TCP, then recreate MinIO
            so it picks up its new root password.

Secrets travel only through a 600-permission file or a process stdin, never as
command-line arguments, and never to stdout.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

REPO = Path.home() / "proof-of-action"
ENV_PATH = REPO / ".env"
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.prod.yml"]
SECRET_KEYS = {"JWT_SECRET", "POSTGRES_PASSWORD", "POA_RUNTIME_DB_PASSWORD", "MINIO_ROOT_PASSWORD"}


def load() -> list[tuple[str, str]]:
    pairs = []
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            pairs.append((key.strip(), value.strip()))
    return pairs


def save(pairs: list[tuple[str, str]]) -> None:
    ENV_PATH.write_text("".join(f"{k}={v}\n" for k, v in pairs))
    os.chmod(ENV_PATH, 0o600)


def get(pairs: list[tuple[str, str]], key: str) -> str:
    return dict(pairs)[key]


def render(key: str, value: str) -> str:
    if key in SECRET_KEYS:
        return f"<{len(value)} chars, withheld>"
    masked = re.sub(r"://([^:/@]+):[^@]+@", r"://\1:***@", value)
    return masked


def show() -> int:
    for key, value in load():
        print(f"{key} = {render(key, value)}")
    return 0


def socket_psql(sql: str, user: str, database: str) -> str:
    proc = subprocess.run(
        ["docker", "exec", "-i", "pofa_db", "psql", "-U", user, "-d", database, "-tAc", sql],
        capture_output=True, text=True, cwd=REPO,
    )
    if proc.returncode:
        raise SystemExit(f"psql failed: {proc.stderr.strip()[:200]}")
    return proc.stdout.strip()


def check() -> int:
    pairs = load()
    user, database = get(pairs, "POSTGRES_USER"), get(pairs, "POSTGRES_DB")
    print("identity    :", socket_psql("select current_user", user, database))
    print("tables      :", socket_psql(
        "select count(*) from information_schema.tables where table_schema='public'",
        user, database))
    print("alembic_row :", socket_psql(
        "select count(*) from information_schema.tables "
        "where table_schema='public' and table_name='alembic_version'", user, database) == "1")
    return 0


def tcp_probe(user: str, database: str, secret: str, host: str) -> str:
    """Authenticate over TCP with a DSN handed in on stdin (not argv)."""
    dsn = f"postgresql://{user}:{secret}@{host}/{database}"
    proc = subprocess.run(
        ["docker", "exec", "-i", "pofa_db", "sh", "-c",
         'read DSN; psql "$DSN" -tAc "select current_user, 1"'],
        input=dsn, capture_output=True, text=True, cwd=REPO,
    )
    if proc.returncode:
        raise SystemExit(f"TCP auth failed for {user}: {proc.stderr.strip()[:120]}")
    return proc.stdout.strip()


def rotate() -> int:
    pairs = load()
    owner = get(pairs, "POSTGRES_USER")
    database = get(pairs, "POSTGRES_DB")

    new = {
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "POA_RUNTIME_DB_PASSWORD": secrets.token_hex(24),
        "MINIO_ROOT_PASSWORD": secrets.token_hex(24),
        "JWT_SECRET": secrets.token_hex(32),
    }
    new["POA_MIGRATION_DATABASE_URL"] = (
        f"postgresql+psycopg2://{owner}:{new['POSTGRES_PASSWORD']}@db:5432/{database}"
    )
    new["POA_DATABASE_URL"] = (
        f"postgresql+psycopg2://poa_runtime:{new['POA_RUNTIME_DB_PASSWORD']}@db:5432/{database}"
    )
    save([(k, new.get(k, v)) for k, v in pairs])
    print("env rewritten")

    script_path = Path("/tmp/.poa_rotate.sql")
    script_path.write_text(
        "\\set ON_ERROR_STOP on\n"
        f"ALTER ROLE {owner} WITH PASSWORD '{new['POSTGRES_PASSWORD']}';\n"
    )
    os.chmod(script_path, 0o600)
    try:
        proc = subprocess.run(
            ["docker", "exec", "-i", "pofa_db", "psql", "-U", owner, "-d", database, "-f", "-"],
            stdin=script_path.open(), capture_output=True, text=True, cwd=REPO,
        )
    finally:
        script_path.unlink(missing_ok=True)
    if proc.returncode:
        raise SystemExit(f"ALTER ROLE failed: {proc.stderr.strip()[:200]}")
    print("owner password applied:", proc.stdout.strip().replace("\n", " "))

    print("tcp auth as owner:", tcp_probe(owner, database, new["POSTGRES_PASSWORD"], "localhost"))

    subprocess.run(COMPOSE + ["up", "-d", "--force-recreate", "minio", "minio-init"],
                   check=True, capture_output=True, text=True, cwd=REPO)
    print("minio recreated with new root password")
    return 0


MODES = {"show": show, "check": check, "rotate": rotate}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        raise SystemExit(__doc__)
    sys.exit(MODES[sys.argv[1]]())
