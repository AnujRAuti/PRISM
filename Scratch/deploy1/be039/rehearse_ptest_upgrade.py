"""Rehearse the pofa_test -> head upgrade without touching pofa_test.

Read pofa_test, copy it into a disposable database, upgrade the copy for real,
then run the BE-039 contract tests against the upgraded copy. This is the
evidence that the authorized upgrade of the real database can be given safely.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import armfull  # noqa: E402
from armfull import PROTECTED_NAMES, admin_dsn, compose_value, psql, sh  # noqa: E402

SOURCE = "pofa_test"
CLONE = "poa_disp_ptest"
HEAD = "w3x4y5z6a033"
ADMIN = compose_value("POSTGRES_USER", "postgres")
BACKUP_DIR = Path("D:/CODING/Backups/pofa_local")
STAMP = time.strftime("%Y%m%d-%H%M%S")
DUMP_IN_CONTAINER = f"/tmp/{SOURCE}-{STAMP}.dump"
COUNTS = ("alembic_version", "audit_ledger_events", "projects", "users",
          "organizations", "organizational_units", "retention_holds")


def guard(name: str) -> None:
    assert name not in PROTECTED_NAMES, f"refusing to write to protected database {name}"


def table_count(db: str) -> int:
    return int(psql(db, "select count(*) from information_schema.tables "
                        "where table_schema='public' and table_type='BASE TABLE'"))


def head_of(db: str) -> str:
    return psql(db, "select version_num from alembic_version")


def vocabulary(db: str) -> tuple[bool, int]:
    raw = psql(db, "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conname='ck_audit_ledger_event_type_domain'")
    return "'PROJECT_CREATED'" in raw, raw.count("'") // 2


print(f"SOURCE {SOURCE} head={head_of(SOURCE)} tables={table_count(SOURCE)}")
before = {t: psql(SOURCE, f"select count(*) from {t}") for t in COUNTS}
print("source row counts:", before)
print("source vocabulary allows PROJECT_CREATED / value count:", vocabulary(SOURCE))

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
print("\n[1] pg_dump (read-only against the source)")
sh(["docker", "exec", "pofa_db", "pg_dump", "-U", ADMIN, "-d", SOURCE,
    "--format=custom", "-f", DUMP_IN_CONTAINER])
local_dump = BACKUP_DIR / f"{SOURCE}-{STAMP}.dump"
sh(["docker", "cp", f"pofa_db:{DUMP_IN_CONTAINER}", str(local_dump)])
sh(["docker", "exec", "pofa_db", "rm", "-f", DUMP_IN_CONTAINER])
digest = hashlib.sha256(local_dump.read_bytes()).hexdigest()
print(f"backup: {local_dump} size={local_dump.stat().st_size} sha256={digest[:16]}...")

print("\n[2] restore into a disposable clone")
guard(CLONE)
psql("postgres", f'DROP DATABASE IF EXISTS "{CLONE}"')
psql("postgres", f'CREATE DATABASE "{CLONE}" OWNER "{ADMIN}"')
sh(["docker", "cp", str(local_dump), f"pofa_db:{DUMP_IN_CONTAINER}"])
sh(["docker", "exec", "pofa_db", "pg_restore", "-U", ADMIN, "-d", CLONE,
    "--no-owner", DUMP_IN_CONTAINER])
sh(["docker", "exec", "pofa_db", "rm", "-f", DUMP_IN_CONTAINER])
after_clone = {t: psql(CLONE, f"select count(*) from {t}") for t in COUNTS}
print(f"clone head={head_of(CLONE)} tables={table_count(CLONE)}")
mismatch = {k: (before[k], after_clone[k]) for k in COUNTS if before[k] != after_clone[k]}
print("clone vs source count mismatches:", mismatch or "none")
assert not mismatch, "restore is not faithful"

print("\n[3] alembic upgrade head on the clone (never stamp)")
env = os.environ.copy()
env["DATABASE_URL"] = admin_dsn(CLONE)
res = sh([str(armfull.PYTHON), "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], env=env)
print(res.stdout.strip()[-400:] or res.stderr.strip()[-400:])
print(f"clone head after upgrade={head_of(CLONE)}")
assert head_of(CLONE) == HEAD, "clone did not land on head"
print("clone vocabulary after upgrade:", vocabulary(CLONE))
after_upgrade = {t: psql(CLONE, f"select count(*) from {t}") for t in COUNTS}
drift = {k: (after_clone[k], after_upgrade[k]) for k in COUNTS if after_clone[k] != after_upgrade[k]}
print("rows changed by the upgrade (only alembic_version may move):", drift)

print("\n[4] BE-039 contract tests against the upgraded clone")
env = os.environ.copy()
env.update(armfull.arm_env())
env["TEST_DATABASE_URL"] = admin_dsn(CLONE)
test_res = sh([str(armfull.PYTHON), "-m", "pytest", "-q",
               "tests/integration/test_be039_project_creation_identity.py"], env=env)
print(test_res.stdout.strip()[-900:] or test_res.stderr.strip()[-900:])
print("pytest exit code:", test_res.returncode)

print("\n[5] does the upgraded clone now really accept PROJECT_CREATED?")
print("ledger rows on clone:", psql(CLONE, "select count(*) from audit_ledger_events"),
      "| PROJECT_CREATED rows:",
      psql(CLONE, "select count(*) from audit_ledger_events where event_type='PROJECT_CREATED'"))
print("projects rows on clone:", psql(CLONE, "select count(*) from projects"))
