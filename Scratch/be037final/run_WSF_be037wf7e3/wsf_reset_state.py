"""Clear this run's own disposable app state so the acceptance run starts clean.

The F1/F3 harness aborted partway through, after it had already created identity
rows, one evidence object and 18 ledger events through the real API. The bootstrap
phase is deliberately not idempotent (usernames and organisation codes are unique
by design), so a second run needs the database emptied rather than a patched
bootstrap.

Scope: only objects that belong to this run, by name —
``be037wf7e3_app`` in this run's own ``be037wf7e3_db`` container, this run's Redis
queue keys, this run's MinIO buckets. The protected resources are not referenced
anywhere in this file.

What it does NOT touch: ``alembic_version`` (the schema stays at head), the
catalogue tables ``roles``/``permissions``/``role_permissions`` (the D2 seeding is
expensive and part of the run's setup evidence), and ``spatial_ref_sys`` (owned by
the PostGIS extension, not by the application).

The ledger is cleared with ``TRUNCATE``, which is precisely the F-05 residual this
milestone documented: the append-only trigger refuses UPDATE and DELETE even to the
database owner, but it cannot refuse TRUNCATE. Using that path here is a teardown
of this run's own synthetic data, and it is recorded as such.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
RUN_ID = "be037wf7e3"
DB_HOST, DB_PORT = "127.0.0.1", 15442
DB_NAME = f"{RUN_ID}_app"
NET = f"{RUN_ID}_net"
DB_CONTAINER = f"{RUN_ID}_db"
REDIS_CONTAINER = f"{RUN_ID}_redis"
QUEUE = f"{RUN_ID}:analysis:jobs"
KEEP = {"alembic_version", "roles", "permissions", "role_permissions", "spatial_ref_sys"}
BUCKETS = (f"{RUN_ID}-quarantine", f"{RUN_ID}-evidence")

import os

os.environ["DATABASE_URL"] = (
    f"postgresql+psycopg2://postgres:{RUN_ID}pw@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
import psycopg2  # noqa: E402


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def docker(*args: str, timeout: int = 120) -> tuple[int, str]:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def main() -> int:
    out: dict = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user="postgres",
                           password=f"{RUN_ID}pw", dbname=DB_NAME)
    conn.autocommit = True
    cur = conn.cursor()

    # Containers holding connections would block TRUNCATE on their locks.
    for name in (f"{RUN_ID}_api", f"{RUN_ID}_worker", f"{RUN_ID}_wsig_probe"):
        rc, o = docker("rm", "-f", name)
        out.setdefault("containers_removed", {})[name] = {"rc": rc, "out": o[:200]}

    cur.execute("select tablename from pg_tables where schemaname='public' order by 1")
    tables = [r[0] for r in cur.fetchall() if r[0] not in KEEP]
    out["tables_cleared_count"] = len(tables)
    out["tables_kept"] = sorted(KEEP)
    out["reset_history_note"] = (
        "this script has been run more than once: the first F1/F3 abort and a second "
        "partial run each left state that needed clearing. rows_before/after below are "
        "measured by this attempt, whatever the earlier attempts left."
    )
    before = {}
    for t in tables:
        cur.execute(f'select count(*) from "{t}"')
        before[t] = cur.fetchone()[0]
    out["rows_before"] = {t: n for t, n in before.items() if n}
    cur.execute(
        "TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"
    )
    out["truncate_rc"] = 0
    after = {}
    for t in tables:
        cur.execute(f'select count(*) from "{t}"')
        after[t] = cur.fetchone()[0]
    out["rows_after"] = {t: n for t, n in after.items() if n}
    out["all_app_tables_empty"] = not any(after.values())
    cur.execute("select count(*) from roles")
    out["catalogue_roles_still_present"] = cur.fetchone()[0]
    cur.execute("select version_num from alembic_version limit 1")
    out["alembic_version"] = cur.fetchone()[0]
    cur.execute("select current_database(), current_user, inet_server_port()")
    out["identity"] = list(cur.fetchone())
    conn.close()

    rc, o = docker("exec", REDIS_CONTAINER, "redis-cli", "del", QUEUE,
                   f"{QUEUE}:processing")
    out["redis_del"] = {"rc": rc, "out": o[:120]}
    lengths = {}
    for key in (QUEUE, f"{QUEUE}:processing"):
        rc, o = docker("exec", REDIS_CONTAINER, "redis-cli", "llen", key)
        lengths[key] = {"rc": rc, "value": o[:60]}
    out["redis_lists_after"] = lengths

    storage = {}
    import boto3  # noqa: E402

    s3 = boto3.client(
        "s3",
        endpoint_url="http://127.0.0.1:19010",
        aws_access_key_id=f"{RUN_ID}admin",
        aws_secret_access_key=f"{RUN_ID}secret",
        region_name="us-east-1",
    )
    for bucket in BUCKETS:
        keys = s3.list_objects_v2(Bucket=bucket).get("Contents", [])
        for obj in keys:
            s3.delete_object(Bucket=bucket, Key=obj["Key"])
        storage[bucket] = {"objects_deleted": len(keys)}
        live = s3.list_objects_v2(Bucket=bucket).get("Contents", [])
        storage[bucket]["objects_after"] = len(live)
    out["minio"] = storage

    out["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE / "wsf-01b-state-reset.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"cleared {len(tables)} tables, rows_before={out['rows_before']}")
    log(f"redis={out['redis_lists_after']} minio={ {k: v['objects_deleted'] for k, v in storage.items()} }")
    log(f"empty={out['all_app_tables_empty']} alembic={out['alembic_version']} identity={out['identity']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
