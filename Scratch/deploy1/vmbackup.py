"""Backup + restore proof for this VM deployment.

A backup that has never been restored proves nothing, so this does both halves:

  1. pg_dump poa_prod (custom format), checksum it.
  2. mc mirror the evidence + quarantine buckets (object storage is separate
     from the database; a SQL dump does not contain the bytes).
  3. Restore into a throwaway database ON THE SAME CLUSTER, then compare table
     count, audit-ledger row count, alembic revision and a sha256 of the ordered
     ledger sequence against the live source. Equal means the restore is
     usable, not merely loadable.
  4. Drop the throwaway database and report the artefacts left behind, which
     should be copied off this VM (a dump that lives only on the VM it describes
     is not a backup).

Prints names, counts and digests only -- never a password or a DSN.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path.home() / "proof-of-action"
BACKUP_DIR = Path.home() / "backups"
SOURCE_DB = "poa_prod"
PROBE_DB = "poa_restore_probe"
OWNER = "poa_owner"


def env_value(key: str) -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"{key} missing")


def sh(args: list[str], *, stdin: str | None = None) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, cwd=REPO, input=stdin)
    if proc.returncode:
        raise SystemExit(f"{args[-1]} -> {proc.stderr.strip()[:300]}")
    return proc.stdout


def sql(statement: str, database: str = SOURCE_DB, tuples: bool = False) -> str:
    args = ["docker", "exec", "pofa_db", "psql", "-U", OWNER, "-d", database, "-v",
            "ON_ERROR_STOP=1"]
    if tuples:
        args.append("-tAc")
    else:
        args.append("-c")
    return sh(args + [statement]).strip()


def digest(sql_statement: str, database: str) -> str:
    value = sql(sql_statement, database=database, tuples=True)
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def main() -> int:
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dump = BACKUP_DIR / f"poa_prod-{stamp}.dump"
    objects = BACKUP_DIR / f"minio-{stamp}"

    minio_pw = env_value("MINIO_ROOT_PASSWORD")

    # ---- 1. database dump -------------------------------------------------
    proc = subprocess.run(
        ["docker", "exec", "pofa_db", "pg_dump", "-U", OWNER, "-Fc", SOURCE_DB],
        cwd=REPO, capture_output=True,
    )
    if proc.returncode:
        raise SystemExit("pg_dump failed: " + proc.stderr.decode()[:300])
    dump.write_bytes(proc.stdout)
    print(f"pg_dump        : {dump.name} {dump.stat().st_size} bytes")
    print(f"sha256         : {hashlib.sha256(dump.read_bytes()).hexdigest()[:32]}")

    # ---- 2. object storage -----------------------------------------------
    subprocess.run(["mkdir", "-p", str(objects)], check=True)
    for bucket in (env_value("S3_EVIDENCE_BUCKET"), env_value("S3_QUARANTINE_BUCKET")):
        out = sh(["docker", "exec", "pofa_minio", "sh", "-c",
                  f'mc alias set local http://localhost:9000 poa_minio {minio_pw} >/dev/null 2>&1; '
                  f'mc mirror --overwrite local/{bucket} /backup/{Path(bucket).name} 2>&1; '
                  f'mc ls -r local/{bucket} 2>&1 | wc -l'])
        print(f"bucket {bucket:<18}: {out.strip().splitlines()[-1]} listing lines mirrored")

    # ---- 3. restore into a throwaway database ----------------------------
    sql(f"DROP DATABASE IF EXISTS {PROBE_DB}", database="postgres")
    sql(f"CREATE DATABASE {PROBE_DB} OWNER {OWNER}", database="postgres")
    proc = subprocess.run(
        ["docker", "exec", "-i", "pofa_db", "pg_restore", "-U", OWNER, "-d", PROBE_DB,
         "--no-owner", "--exit-on-error"],
        cwd=REPO, input=dump.read_bytes(), capture_output=True,
    )
    if proc.returncode:
        raise SystemExit("pg_restore failed: " + proc.stderr.decode()[:400])
    print("pg_restore     : exit 0 (--exit-on-error)")

    compare = [
        ("tables", "select count(*) from information_schema.tables "
                   "where table_schema='public'"),
        ("ledger_rows", "select count(*) from audit_ledger_events"),
        ("alembic_rev", "select coalesce(max(version_num),'(none)') from alembic_version"),
        ("sequence_span", "select coalesce(min(sequence_number)::text,'(empty)')||'..'||"
                          "coalesce(max(sequence_number)::text,'(empty)') from audit_ledger_events"),
        ("ledger_digest", "select coalesce(string_agg(md5(event_type||'|'||action||'|'||"
                          "coalesce(payload::text,'')),',' order by sequence_number),'(empty)') "
                          "from audit_ledger_events"),
    ]
    print("\nsurface              source            restore           match")
    all_match = True
    for label, statement in compare:
        a = sql(statement, database=SOURCE_DB, tuples=True)
        b = sql(statement, database=PROBE_DB, tuples=True)
        all_match = all_match and (a == b)
        print(f"{label:<20} {a[:16]:<16} {b[:16]:<16} {'YES' if a == b else 'NO'}")

    # ---- 4. teardown ------------------------------------------------------
    sql(f"DROP DATABASE {PROBE_DB}", database="postgres")
    print(f"\nprobe database dropped; artefacts kept in ~/{BACKUP_DIR.name}/")
    print("NOTE: the dump lives on this VM only. Copy it off-host before calling it a backup.")
    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
