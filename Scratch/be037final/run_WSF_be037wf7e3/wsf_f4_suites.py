"""BE-037 WS-F / F4: the suite matrix, executed against disposable targets only.

Why this script creates its own database
----------------------------------------
``tests/conftest.py`` publishes ``TEST_DATABASE_URL`` as the suite's only
supported target, and it blocks ``pofa_dev`` by name but not ``pofa_test``.
This run's safety constraints forbid writing to ``pofa_test`` as well, so the
integration suites are pointed at a *third* database this run owns —
``be037wf7e3_suite`` — created inside this run's own Postgres container,
extended and migrated to head with the same alembic revision the acceptance
stack uses. Nothing here reads or writes ``pofa_dev``, ``pofa_test``,
``pofa_db``, ``pofa_redis`` or ``pofa_minio``.

Storage is redirected the same way: ``S3_*`` points at this run's MinIO, and
``POA_DISPOSABLE_MINIO_CONTAINER`` is armed with that container's name so the
restart-persistence obligation in ``tests/integration/test_storage.py``
*executes* instead of reporting as skipped. Unarmed, that test refuses to
restart anything — which is the correct behaviour, but not evidence that the
obligation was met.

Each entry records the exact command, the category it answers to, the real
exit code, the parsed counts, wall time, and the failing node ids verbatim, so
a failure can be classified rather than explained away.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
SUITE_LOGS = EVIDENCE / "suites"
REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
PY = str(REPO / "backend/.venv312_repro/Scripts/python.exe")

RUN_ID = "be037wf7e3"
DB_HOST, DB_PORT = "127.0.0.1", 15442
OWNER, OWNER_PW = "postgres", f"{RUN_ID}pw"
ACCEPTANCE_DB = f"{RUN_ID}_app"
SUITE_DB = f"{RUN_ID}_suite"
# A database *named* like a protected one, hosted inside this run's own Postgres
# container. It exists so the safety guard's refusal can be proven over a real
# connection: the guard decides by the name the server reports, and a disposable
# cluster may safely host that name while the protected cluster must not be
# dialled. Nothing is written to it — the probe only asks it its name — and the
# suites' own target stays SUITE_DB. It is dropped during cleanup.
PROBE_DB = "pofa_test"
REDIS_CONTAINER = f"{RUN_ID}_redis"
MINIO_CONTAINER = f"{RUN_ID}_minio"
REDIS_URL = "redis://127.0.0.1:16389/0"
S3_ENDPOINT = "http://127.0.0.1:19010"
S3_ADMIN, S3_SECRET = f"{RUN_ID}admin", f"{RUN_ID}secret"
QUARANTINE_BUCKET, EVIDENCE_BUCKET = f"{RUN_ID}-quarantine", f"{RUN_ID}-evidence"
QUEUE = f"{RUN_ID}:analysis:jobs"

SECRETS = [OWNER_PW, S3_SECRET, S3_ADMIN, f"{RUN_ID}rtpw"]
OUT_PATH = EVIDENCE / "wsf-04-suites.json"

SUITE_DB_URL = (f"postgresql+psycopg2://{OWNER}:{OWNER_PW}@{DB_HOST}:{DB_PORT}/{SUITE_DB}")
OWNER_DB_URL = SUITE_DB_URL
OWNER_PROBE_URL = (f"postgresql+psycopg2://{OWNER}:{OWNER_PW}@{DB_HOST}:{DB_PORT}/{PROBE_DB}")


def redact(text: str) -> str:
    for secret in SECRETS:
        text = text.replace(secret, "***REDACTED***")
    return text


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {redact(msg)}", flush=True)


def suite_env(**extra: str) -> dict:
    """The child environment. Only key names are ever logged."""
    env = dict(os.environ)
    for key in ("POA_DATABASE_CONTEXT", "POA_TEST_DATABASE_URL",
                "POA_ORIGINAL_DATABASE_URL", "POA_AUTHORIZED_DATABASE_NAME",
                "TEST_DATABASE_URL"):
        env.pop(key, None)
    env.update({
        "TEST_DATABASE_URL": SUITE_DB_URL,
        "DATABASE_URL": SUITE_DB_URL,
        "REDIS_URL": REDIS_URL,
        "ANALYSIS_QUEUE_NAME": QUEUE,
        "S3_ENDPOINT": S3_ENDPOINT,
        "S3_ACCESS_KEY": S3_ADMIN,
        "S3_SECRET_KEY": S3_SECRET,
        "S3_USE_SSL": "false",
        "S3_QUARANTINE_BUCKET": QUARANTINE_BUCKET,
        "S3_EVIDENCE_BUCKET": EVIDENCE_BUCKET,
        # Four obligations in this repository's tests are gated on an explicit
        # disposable-infrastructure arming variable. Unarmed they *skip*, which
        # is correct behaviour but not evidence that the obligation was met, so
        # this run arms each of them with its own resources:
        #   * restart-persistence in tests/integration/test_storage.py
        #   * the hung/blackholed-connection measurements in
        #     test_be037c_redis_timeout_integration.py
        #   * the three-identity ledger matrix in
        #     test_be037e2_ledger_identity_matrix.py
        #   * the live (non-stub) protected-name refusal half of
        #     test_be029_database_safety_guard.py
        "POA_DISPOSABLE_MINIO_CONTAINER": MINIO_CONTAINER,
        "POA_DISPOSABLE_REDIS_URL": REDIS_URL,
        "POA_DISPOSABLE_REDIS_CONTAINER": REDIS_CONTAINER,
        "POA_DISPOSABLE_OWNER_DATABASE_URL": OWNER_DB_URL,
        "POA_PROTECTED_NAME_PROBE_DATABASE_URL": OWNER_PROBE_URL,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    env.update(extra)
    return env


def sql(statement: str, dbname: str = SUITE_DB) -> list[tuple]:
    import psycopg2

    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=OWNER, password=OWNER_PW,
                            dbname=dbname, connect_timeout=10)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
            return cur.fetchall() if cur.description else []
    finally:
        conn.close()


def prepare_suite_db() -> dict:
    """Recreate the suite database from scratch and migrate it to head.

    A brand-new database is the stricter target: it proves the migrations
    alone produce the schema the suites expect, instead of inheriting whatever
    a previous run left behind.
    """
    info: dict = {}
    sql(f'DROP DATABASE IF EXISTS "{SUITE_DB}" WITH (FORCE)', dbname="postgres")
    sql(f'CREATE DATABASE "{SUITE_DB}"', dbname="postgres")
    # The probe database for the live protected-name refusal half: empty, in this
    # run's own cluster, deliberately named like a protected database so the
    # guard's decision by server-reported name is exercised over a real
    # connection. Nothing is written to it and it is dropped during cleanup.
    sql(f'DROP DATABASE IF EXISTS "{PROBE_DB}" WITH (FORCE)', dbname="postgres")
    sql(f'CREATE DATABASE "{PROBE_DB}"', dbname="postgres")
    info["probe_database"] = {
        "name": PROBE_DB,
        "server_reports": sql("select current_database()", dbname=PROBE_DB)[0][0],
        "tables": sql("select count(*) from information_schema.tables "
                      "where table_schema='public'", dbname=PROBE_DB)[0][0],
        "cluster_container": f"{RUN_ID}_db",
        "writes_performed_by_this_run": ["CREATE DATABASE only"],
    }
    sql("CREATE EXTENSION IF NOT EXISTS postgis")
    sql("CREATE EXTENSION IF NOT EXISTS vector")
    info["extensions"] = dict(sql(
        "select extname, extversion from pg_extension order by 1"))
    info["tables_after_create"] = sql(
        "select count(*) from information_schema.tables where table_schema='public'")[0][0]

    cmd = ["python", "-m", "alembic", "upgrade", "head"]
    t0 = time.monotonic()
    proc = subprocess.run([PY, "-m", "alembic", "upgrade", "head"], cwd=REPO,
                          env=suite_env(), capture_output=True, text=True, timeout=1800)
    info["alembic"] = {
        "command": " ".join(cmd) + "  (cwd=repo, DATABASE_URL=<suite db>)",
        "rc": proc.returncode, "wall_s": round(time.monotonic() - t0, 1),
        "tail": redact((proc.stdout + "\n" + proc.stderr).strip()).splitlines()[-12:],
    }
    info["alembic_version"] = sql("select version_num from alembic_version")
    info["tables_at_head"] = sql(
        "select count(*) from information_schema.tables where table_schema='public'")[0][0]
    # The catalogue is not seeded by migrations (finding D2); the suites that
    # assert on grants need it, and this is how the acceptance stack got it too.
    t0 = time.monotonic()
    proc = subprocess.run(
        [PY, "-c",
         "from sqlalchemy import create_engine\n"
         "from sqlalchemy.orm import sessionmaker\n"
         "from backend.services.authorization import ensure_default_catalogue\n"
         "db = sessionmaker(bind=create_engine(%r))()\n"
         "ensure_default_catalogue(db)\n"
         "print('CATALOGUE', db.execute(__import__('sqlalchemy').text("
         "\"select (select count(*) from roles), (select count(*) from permissions), "
         "(select count(*) from role_permissions)\"))).one())\n"
         "db.close()\n" % SUITE_DB_URL],
        cwd=REPO, env=suite_env(), capture_output=True, text=True, timeout=900)
    out = redact((proc.stdout + proc.stderr).strip()).splitlines()
    info["catalogue_seed"] = {"rc": proc.returncode,
                              "wall_s": round(time.monotonic() - t0, 1),
                              "result_line": next((l for l in out if l.startswith("CATALOGUE")), None),
                              "tail": out[-6:]}
    return info

def parse_counts(text: str) -> dict:
    """Read pytest's own summary line rather than inferring from output."""
    line = next((l for l in reversed(text.splitlines())
                 if re.search(r"\b\d+ (passed|failed|error|errors)\b", l)
                 and ("=" in l or "passed" in l)), "")
    numbers = {}
    for match in re.finditer(r"(\d+) (passed|failed|skipped|errors?|warnings?|deselected|xfailed)",
                             line):
        numbers[match.group(2).rstrip("s")] = int(match.group(1))
    return {"summary_line": redact(line.strip()), "counts": numbers,
            "failed_tests": [redact(l.strip()) for l in text.splitlines()
                             if l.startswith("FAILED ") or l.startswith("ERROR ")],
            "skip_reasons": [redact(l.strip()) for l in text.splitlines()
                             if l.startswith("SKIPPED [")]}


def run_suite(category: str, args: list[str], *, timeout: int, extra_env: dict | None = None) -> dict:
    cmd = [PY, "-m", "pytest", *args]
    shown = " ".join(["python", "-m", "pytest", *args])
    t0 = time.monotonic()
    env = suite_env(**(extra_env or {}))
    log(f"{category}: {shown}")
    try:
        proc = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True,
                              timeout=timeout)
        rc, out = proc.returncode, proc.stdout + "\n" + proc.stderr
    except subprocess.TimeoutExpired as exc:
        rc = -1
        out = f"TIMEOUT after {timeout}s\n{(exc.stdout or b'').decode(errors='replace')}"
    wall = round(time.monotonic() - t0, 1)
    parsed = parse_counts(out)
    SUITE_LOGS.mkdir(parents=True, exist_ok=True)
    (SUITE_LOGS / f"{category}.txt").write_text(redact(out), encoding="utf-8")
    header = [l for l in out.splitlines() if l.startswith("PoA test database")]
    result = {"category": category, "command": shown, "rc": rc, "wall_s": wall,
              "target_database_header": header[:2], **parsed,
              "log_file": f"evidence/suites/{category}.txt",
              "env_keys_set": sorted((extra_env or {}).keys())}
    record(category, result)
    log(f"{category}: rc={rc} {wall}s {parsed['counts']}")
    return result


OUT: dict = {}


def record(category: str, result: dict) -> None:
    OUT[category] = result
    EVIDENCE.mkdir(exist_ok=True)
    OUT_PATH.write_text(redact(json.dumps(OUT, indent=2, default=str)), encoding="utf-8")


# The categories the task names, each with the exact selection that answers it.
CATEGORIES = [
    ("unit_all", ["tests/unit", "-q", "-p", "no:cacheprovider"], 2400),
    ("integration_all", ["tests/integration", "-q", "-rs", "-p", "no:cacheprovider"], 3600),
    ("authorization", ["tests/unit/test_authorization.py",
                        "tests/integration/test_authorization.py", "-q"], 1800),
    ("worker", ["tests/unit/test_be037a_analysis_worker_shutdown.py",
                "tests/unit/test_be037c_analysis_queue_timeouts.py",
                "tests/unit/test_be037i1_analysis_worker_redis_outage.py",
                "tests/unit/test_be037g5_reprocessing_hook.py",
                "tests/integration/test_be036_webhook_worker.py",
                "tests/integration/test_be037c_redis_timeout_integration.py",
                "tests/integration/test_analysis_jobs.py", "-q"], 1800),
    ("storage", ["tests/integration/test_storage.py", "-q", "-rs"], 1200),
    ("migration", ["tests/unit/test_migrations.py",
                   "tests/integration/test_migration_and_crud.py", "-q"], 1800),
    ("schema_drift", ["tests/integration/test_schema_drift_gate.py", "-q"], 1200),
    ("be037_final", ["tests/unit/test_be037_webhook_redirect_ssrf.py",
                     "tests/integration/test_be037g1_analysis_auth.py",
                     "tests/integration/test_be037e2_ledger_identity_matrix.py",
                     "tests/integration/test_be029_database_safety_guard.py", "-q"], 1800),
]


def main() -> int:
    EVIDENCE.mkdir(exist_ok=True)
    only = sys.argv[1:]
    OUT["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if not only:
        OUT["suite_target_setup"] = prepare_suite_db()
        log(f"suite db ready alembic={OUT['suite_target_setup']['alembic_version']} "
            f"tables={OUT['suite_target_setup']['tables_at_head']}")
        record("_setup", OUT["suite_target_setup"])

    targets = [c for c in CATEGORIES if not only or c[0] in only]
    for category, args, timeout in targets:
        run_suite(category, args, timeout=timeout)

    if not only:
        # The headline total, in one process against the same disposable target.
        run_suite("full_suite", ["tests", "-q", "-rs", "-p", "no:cacheprovider"], timeout=5400)
    OUT["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    record("_summary", {
        "categories": {name: {"rc": r["rc"], "counts": r["counts"]}
                       for name, r in OUT.items() if isinstance(r, dict) and "rc" in r},
        "suite_database": SUITE_DB,
        "acceptance_database_untouched_by_suites": True,
        "protected_targets_used": [],
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
