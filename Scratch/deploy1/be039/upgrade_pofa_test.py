"""Authorized: upgrade the real pofa_test v2w3x4y5z032 -> w3x4y5z6a033.

Ordering the owner requires: prove the backup is current and archive-readable,
prove the connection really points at pofa_test, run the real alembic path (no
stamping), then verify the revision and all 97 allowed event types. No test runs
that write synthetic projects into this database.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, r"D:/CODING/Projects/Proof-Of-Action-Final")
sys.path.insert(0, r"D:/CODING/Scratch/deploy1")

import armfull  # noqa: E402
from armfull import admin_dsn, compose_value, psql, sh  # noqa: E402
from backend.db.models import AUDIT_EVENT_TYPES  # noqa: E402

TARGET = "pofa_test"
EXPECT_FROM = "v2w3x4y5z032"
EXPECT_TO = "w3x4y5z6a033"
BACKUP = Path(r"D:/CODING/Backups/pofa_local/pofa_test-20261017-201758.dump")
EXPECT_SHA = "dac2e359870c1b478c154aa3675c23cfc63c3e3373f1324c510e78e7be78acf6"
TABLE_COUNT = ("select count(*) from information_schema.tables "
               "where table_schema='public' and table_type='BASE TABLE'")


def all_counts(db: str) -> dict[str, str]:
    names = psql(db, "select table_name from information_schema.tables "
                     "where table_schema='public' and table_type='BASE TABLE' "
                     "order by table_name").splitlines()
    return {n: psql(db, f'select count(*) from "{n}"') for n in names}

def vocabulary(db: str) -> set[str]:
    raw = psql(db, "select pg_get_constraintdef(oid) from pg_constraint where "
                   "conname='ck_audit_ledger_event_type_domain'")
    return set(re.findall(r"'([^']+)'", raw))


dsn = admin_dsn(TARGET)
parsed = re.match(r"postgresql\+psycopg2://([^:]+):[^@]*@([^:/]+):(\d+)/(.+)$", dsn)
print(f"[0] connection target: user={parsed.group(1)} host={parsed.group(2)} "
      f"port={parsed.group(3)} database={parsed.group(4)}")
assert parsed.group(4) == TARGET, "DATABASE_URL does not point at pofa_test"

sha = hashlib.sha256(BACKUP.read_bytes()).hexdigest()
print(f"[1] backup {BACKUP.name} size={BACKUP.stat().st_size} sha256={sha[:16]}...")
assert sha == EXPECT_SHA, "backup digest differs from the one whose restore was proven"

IN_CONTAINER = "/tmp/verify_pofa_test.dump"
sh(["docker", "cp", str(BACKUP), f"pofa_db:{IN_CONTAINER}"])
listing = sh(["docker", "exec", "pofa_db", "pg_restore", "--list", IN_CONTAINER]).stdout
objects = [l for l in listing.splitlines() if l and not l.startswith(";")]
sh(["docker", "exec", "pofa_db", "rm", "-f", IN_CONTAINER])
print(f"    pg_restore --list parses the archive: {len(objects)} restorable entries")
assert len(objects) > 50, "archive listing is not readable"

before_head = psql(TARGET, "select version_num from alembic_version")
print(f"[2] pofa_test before: head={before_head} tables={psql(TARGET, TABLE_COUNT)}")
assert before_head == EXPECT_FROM, f"unexpected starting revision {before_head}"
before = all_counts(TARGET)
print(f"    before: {len(before)} base tables snapshotted, "
      f"audit_ledger_events={before['audit_ledger_events']}, projects={before['projects']}")
before_vocab = vocabulary(TARGET)
print(f"    before vocabulary: {len(before_vocab)} types, PROJECT_CREATED allowed: "
      f"{'PROJECT_CREATED' in before_vocab}")

print("[3] alembic upgrade head (real path, no stamp)")
env = os.environ.copy()
env["DATABASE_URL"] = dsn
res = sh([str(armfull.PYTHON), "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
         env=env)
print("    " + (res.stdout.strip() or res.stderr.strip()).splitlines()[-1])

after_head = psql(TARGET, "select version_num from alembic_version")
print(f"[4] pofa_test after: head={after_head} tables={psql(TARGET, TABLE_COUNT)}")
assert after_head == EXPECT_TO, f"did not land on head ({after_head})"
print("    alembic heads:",
      sh([str(armfull.PYTHON), "-m", "alembic", "-c", "alembic.ini", "heads"],
         env=env).stdout.strip())

raw = psql(TARGET, "select pg_get_constraintdef(oid) from pg_constraint where "
                   "conname='ck_audit_ledger_event_type_domain'")
live = set(re.findall(r"'([^']+)'", raw))
print(f"[5] vocabulary now: {len(live)} types | PROJECT_CREATED allowed: "
      f"{'PROJECT_CREATED' in live} | code vocabulary: {len(AUDIT_EVENT_TYPES)}")
print("    live == code exactly:", live == set(AUDIT_EVENT_TYPES))
print("    added by the migration:", sorted(live - before_vocab) or "none")
print("    DROPPED by the migration (must be none):", sorted(before_vocab - live) or "none")

after = all_counts(TARGET)
drift = {k: (before[k], after[k]) for k in before if before[k] != after.get(k)}
missing = sorted(set(before) - set(after))
print(f"[6] base tables changed by the migration (expect none): {drift or 'none'}"
      f" | tables lost: {missing or 'none'} | {len(after)} tables after")
assert not drift and not missing, "the migration changed data or dropped a table"
print("    PROJECT_CREATED rows now in pofa_test:",
      psql(TARGET, "select count(*) from audit_ledger_events "
                   "where event_type='PROJECT_CREATED'"))

print("[7] schema-drift re-check after the DDL (read-only autogenerate)")
chk = sh([str(armfull.PYTHON), "-m", "alembic", "-c", "alembic.ini", "check"],
         env=env, quiet=True)
out = (chk.stdout.strip() or chk.stderr.strip()).splitlines()
print("    rc=", chk.returncode, "|", out[-1] if out else "no output")
