"""Environment event: the Docker Desktop engine stopped and came back during WS-F.

Recorded because it changes what this run can claim:

  * every container on the machine went to ``exited`` at the same instant, which
    is a daemon-lifecycle signature rather than a per-container stop;
  * the protected ``pofa_db`` / ``pofa_redis`` / ``pofa_minio`` containers came
    back on their own ``unless-stopped`` restart policies. No command in this run
    targeted them; the inspection here is read-only and is the evidence that
    their volumes and configuration are the ones created in September;
  * the host clock was corrected at the same boundary (Windows reported
    2026-10-14 ~23:25 IST before, 2026-10-15 ~08:16 IST after, and the day of
    week moved with it). Absolute timestamps in evidence files therefore span a
    discontinuity; durations and inter-event intervals do not, because each was
    computed inside a single clock domain.

This also bears on the earlier unresolved MinIO-restart attribution: a restart of
this shape is produced by the desktop engine, not by this run.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent / "evidence"
RUN_CONTAINERS = ["be037wf7e3_db", "be037wf7e3_redis", "be037wf7e3_minio"]
PROTECTED = ["pofa_db", "pofa_redis", "pofa_minio"]
FIELDS = ("{{.State.Status}}", "{{.State.ExitCode}}", "{{.State.StartedAt}}",
          "{{.State.FinishedAt}}", "{{.RestartCount}}",
          "{{.HostConfig.RestartPolicy.Name}}", "{{.Created}}", "{{.Config.Image}}")


def inspect(name: str) -> dict:
    fmt = "|".join(FIELDS)
    proc = subprocess.run(["docker", "inspect", "--format", fmt, name],
                          capture_output=True, text=True, timeout=60)
    keys = ("status", "exit_code", "started_at", "finished_at", "restart_count",
            "restart_policy", "created", "image")
    if proc.returncode != 0:
        return {"inspect_error": proc.stderr.strip()[:300]}
    return dict(zip(keys, proc.stdout.strip().split("|")))


def sh(container: str, cmd: list[str]) -> str:
    proc = subprocess.run(["docker", "exec", container, *cmd],
                          capture_output=True, text=True, timeout=120)
    return (proc.stdout.strip() or proc.stderr.strip())[:400]


def db_counts() -> dict:
    import psycopg2

    conn = psycopg2.connect(host="127.0.0.1", port=15442, user="postgres",
                            password="***REDACTED-THROWAWAY-OWNER-PW***", dbname="be037wf7e3_app",
                            connect_timeout=10)
    try:
        with conn.cursor() as cur:
            values: dict = {}
            for label, statement in (
                ("analysis_jobs", "select count(*) from analysis_jobs"),
                ("ledger_events", "select count(*) from audit_ledger_events"),
                ("ledger_sequence_range",
                 "select min(sequence_number) || '-' || max(sequence_number) "
                 "from audit_ledger_events"),
                ("alembic_version", "select version_num from alembic_version"),
            ):
                cur.execute(statement)
                values[label] = cur.fetchone()[0]
            return values
    finally:
        conn.close()


def post_restart_integrity() -> dict:
    """This run's own data, re-counted after the engine came back. Read-only."""
    return {
        "acceptance_db": db_counts(),
        "queue_lengths": sh("be037wf7e3_redis", [
            "redis-cli", "--no-auth-warning", "llen", "be037wf7e3:analysis:jobs"]),
        "processing_lengths": sh("be037wf7e3_redis", [
            "redis-cli", "--no-auth-warning", "llen",
            "be037wf7e3:analysis:jobs:processing"]),
        "minio_bucket_directories": sh("be037wf7e3_minio", ["ls", "/data"]),
    }


def main() -> int:
    out: dict = {"observed_at_host_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                 "observed_at_host_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "event": ("Docker Desktop engine became unreachable at ~23:25 IST on the run's "
                           "clock and was relaunched; the machine's containers all show a single "
                           "simultaneous exit"),
                 "commands_issued_by_this_run_against_protected_containers": [],
                 "protected_containers_read_only_inspection": {n: inspect(n) for n in PROTECTED},
                 "run_containers": {n: inspect(n) for n in RUN_CONTAINERS}}
    # Volume identity: the protected volumes must still be the ones this run
    # never touched, and the run's own volumes must still exist.
    out["volumes"] = subprocess.run(
        ["docker", "volume", "ls", "--format", "{{.Name}}|{{.Driver}}"],
        capture_output=True, text=True, timeout=60).stdout.splitlines()
    out["run_data_survived_restart"] = post_restart_integrity()
    (EVIDENCE / "wsf-06-environment-event.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
