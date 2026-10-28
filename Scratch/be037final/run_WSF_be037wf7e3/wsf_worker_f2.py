"""BE-037 WS-F / F2: the I1 outage matrix and the BE-037 shutdown matrix, measured
on this run's acceptance stack (`be037wf7e3`), on the current image.

Why containers rather than host processes: the worker's shutdown contract is a
SIGTERM handler at container PID 1, and Windows hosts cannot deliver SIGTERM to a
host process at all (Python's ``os.kill`` maps it to TerminateProcess). The only
honest place to measure the promised behaviour is the deployment shape itself.

Why ``docker stop``/``docker start`` on this run's own Redis container: those are
the only primitives here that produce a real outage. Network disconnect and
``compose up -d`` were both measured (in the engineering run) to leave the
connection alive, so they would have proven nothing.

Every number reported is read back from the containers and the database:
  * retry intervals — parsed from the worker's own warning lines, and their wall
    clock spacing from ``docker logs --timestamps``;
  * exit codes, states and RestartCount — from ``docker inspect``;
  * shutdown latency — measured around ``docker stop``;
  * queue/processing lengths — ``LLEN`` against this run's Redis;
  * jobs recovered and final states — ``analysis_jobs`` rows.

Credentials for this run's disposable stack are passed with ``--env-file`` so they
never appear in a command line, a log or an evidence file, and ``redact()`` covers
every value this script knows.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
PY = str(REPO / "backend/.venv312_repro/Scripts/python.exe")

RUN_ID = "be037wf7e3"
NETWORK = f"{RUN_ID}_net"
IMAGE = "poa-backend:be037final"
DB_HOST, DB_PORT, DB_NAME = "127.0.0.1", 15442, f"{RUN_ID}_app"
OWNER_PW = f"{RUN_ID}pw"
RUNTIME_ROLE, RUNTIME_PW = f"{RUN_ID}_runtime", f"{RUN_ID}rtpw"
REDIS_CONTAINER = f"{RUN_ID}_redis"
REDIS_HOST_URL = "redis://127.0.0.1:16389/0"
QUEUE = f"{RUN_ID}:analysis:jobs"
PROCESSING = f"{QUEUE}:processing"
ENV_FILE = HERE / "f2-worker.env"

# The worker's in-network DSN uses the run-scoped runtime role, i.e. the same
# identity shape production would use — not the database owner.
WORKER_DB_URL = f"postgresql+psycopg2://{RUNTIME_ROLE}:{RUNTIME_PW}@db:5432/{DB_NAME}"
SECRETS = [OWNER_PW, RUNTIME_PW, f"{RUN_ID}secret", f"{RUN_ID}admin"]

BASE_WORKER_ENV = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": WORKER_DB_URL,
    "REDIS_URL": "redis://redis:6379/0",
    "S3_ENDPOINT": "http://minio:9000",
    "S3_ACCESS_KEY": f"{RUN_ID}admin",
    "S3_SECRET_KEY": f"{RUN_ID}secret",
    "S3_USE_SSL": "false",
    "S3_QUARANTINE_BUCKET": f"{RUN_ID}-quarantine",
    "S3_EVIDENCE_BUCKET": f"{RUN_ID}-evidence",
    "ANALYSIS_QUEUE_NAME": QUEUE,
    "ANALYSIS_REDIS_SOCKET_TIMEOUT_SECONDS": "30",
    "ANALYSIS_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS": "5",
    "ANALYSIS_REDIS_HEALTH_CHECK_INTERVAL_SECONDS": "15",
    "ANALYSIS_DEQUEUE_BLOCK_SECONDS": "5",
    "ANALYSIS_RETRY_BACKOFF_BASE_SECONDS": "5",
    "ANALYSIS_RETRY_BACKOFF_MAX_SECONDS": "60",
    "ANALYSIS_SHUTDOWN_POLL_SECONDS": "0.5",
    "ANALYSIS_ABANDONED_TIMEOUT_SECONDS": "300",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}

EVIDENCE_PATH = EVIDENCE / "wsf-03-f2.json"


def redact(text: str) -> str:
    for secret in SECRETS:
        text = text.replace(secret, "***REDACTED***")
    return text


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {redact(msg)}", flush=True)


def docker(*args: str, timeout: int = 300) -> tuple[int, str]:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=timeout)
    return proc.returncode, redact((proc.stdout + proc.stderr).strip())


def record(name: str, payload: dict) -> dict:
    EVIDENCE.mkdir(exist_ok=True)
    existing = {}
    if EVIDENCE_PATH.exists():
        existing = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    existing[name] = payload
    existing.setdefault("run_id", RUN_ID)
    EVIDENCE_PATH.write_text(redact(json.dumps(existing, indent=2, default=str)),
                             encoding="utf-8")
    log(f"recorded {name}")
    return existing


# ---------------------------------------------------------------------------
# fixtures: real synthetic objects, real jobs
# ---------------------------------------------------------------------------


def app_env() -> None:
    import os

    os.environ.update({
        "ENVIRONMENT": "development",
        "DATABASE_URL": f"postgresql+psycopg2://postgres:{OWNER_PW}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
        "REDIS_URL": REDIS_HOST_URL,
        "S3_ENDPOINT": "http://127.0.0.1:19010",
        "S3_ACCESS_KEY": f"{RUN_ID}admin",
        "S3_SECRET_KEY": f"{RUN_ID}secret",
        "S3_USE_SSL": "false",
        "S3_QUARANTINE_BUCKET": f"{RUN_ID}-quarantine",
        "S3_EVIDENCE_BUCKET": f"{RUN_ID}-evidence",
        "ANALYSIS_QUEUE_NAME": QUEUE,
    })
    sys.path.insert(0, str(REPO))


def fixture(size_px: int = 240) -> dict:
    """Store a real JPEG in this run's MinIO and queue a real job for it."""
    import uuid

    from PIL import Image

    app_env()
    from backend.services.storage import StorageService

    evidence_id = str(uuid.uuid4())
    rng = random.Random(evidence_id)
    img = Image.new("RGB", (size_px, size_px))
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256))
                 for _ in range(size_px * size_px)])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    data = buf.getvalue()

    storage = StorageService()
    storage.ensure_buckets()
    key = storage.quarantine_key(evidence_id)
    storage.put_object(storage.quarantine_bucket, key, data, content_type="image/jpeg")

    from sqlalchemy.orm import sessionmaker

    from backend.db.models import AnalysisJob, Evidence
    from backend.db.session import get_engine

    Session = sessionmaker(bind=get_engine())
    db = Session()
    try:
        db.add(Evidence(id=evidence_id, filename=f"{evidence_id}.jpg",
                        content_type="image/jpeg", storage_key=key,
                        file_size=len(data), status="uploaded_quarantine"))
        job = AnalysisJob(evidence_id=evidence_id, status="queued")
        db.add(job)
        db.commit()
        job_id = str(job.id)
    finally:
        db.close()
    return {"evidence_id": evidence_id, "job_id": job_id, "bytes": len(data),
            "storage_key": key}


def redis_cli(*args: str) -> str:
    _, out = docker("exec", REDIS_CONTAINER, "redis-cli", *args, timeout=60)
    return out


def enqueue(job_id: str) -> None:
    redis_cli("rpush", QUEUE, '{"job_id":"%s"}' % job_id)


def lists() -> dict:
    return {"queue": redis_cli("llen", QUEUE), "processing": redis_cli("llen", PROCESSING)}


def clear_lists() -> None:
    redis_cli("del", QUEUE, PROCESSING)


def job_states() -> dict:
    app_env()
    from sqlalchemy import create_engine, text

    engine = create_engine(
        f"postgresql+psycopg2://postgres:{OWNER_PW}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    with engine.connect() as conn:
        rows = conn.execute(text(
            "select j.id, j.status, j.attempt_count, j.error, "
            "(select count(*) from analysis_results r where r.job_id = j.id) as results "
            "from analysis_jobs j order by j.created_at")).mappings().all()
    return {str(r["id"]): {"status": r["status"], "attempt_count": r["attempt_count"],
                           "error": r["error"], "result_rows": r["results"]}
            for r in rows}


def worker_identities() -> list:
    """Prove which database identity the worker connected as."""
    import psycopg2

    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user="postgres",
                            password=OWNER_PW, dbname=DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select usename, application_name, state, count(*) from pg_stat_activity "
                "where datname = %s group by 1,2,3 order by 4 desc", (DB_NAME,))
            return list(cur.fetchall())
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# worker containers
# ---------------------------------------------------------------------------


def start_worker(name: str, **overrides: str) -> dict:
    docker("rm", "-f", name)
    env = dict(BASE_WORKER_ENV)
    env.update(overrides)
    ENV_FILE.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n",
                        encoding="utf-8")
    rc, out = docker("run", "-d", "--name", name, "--network", NETWORK, "--restart", "no",
                     "--env-file", str(ENV_FILE), IMAGE,
                     "python", "-m", "backend.workers.analysis_worker")
    if rc != 0:
        raise RuntimeError(f"docker run failed rc={rc} out={out[:400]}")
    facts = inspect_all(name)
    log(f"started {name} id={facts['id'][:12]}")
    return {"container": name, "configured": {**env, **{k: "***" for k in ()}}, **facts}


def inspect_all(name: str) -> dict:
    _, out = docker("inspect", "-f",
                    "{{.Id}}|{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}"
                    "|{{.RestartCount}}|{{.State.StartedAt}}|{{.State.FinishedAt}}",
                    name)
    parts = out.split("|")
    if len(parts) != 7:
        return {"id": None, "state": "absent", "exit_code": None, "oom_killed": None,
                "restart_count": None, "started_at": None, "finished_at": None}
    return {"id": parts[0], "state": parts[1], "exit_code": parts[2],
            "oom_killed": parts[3], "restart_count": parts[4], "started_at": parts[5],
            "finished_at": parts[6]}


def logs(name: str, timestamps: bool = True) -> list[str]:
    args = ["logs"] + (["--timestamps"] if timestamps else []) + [name]
    _, out = docker(*args, timeout=90)
    return out.splitlines()


WARN = "redis unavailable; backing off"


def warnings(name: str) -> list[dict]:
    """Every outage warning with its stated delay and measured timestamp."""
    rows = []
    for line in logs(name):
        if WARN in line:
            stamp = line.split(" ", 1)[0] if timestamps_ok(line) else None
            match = re.search(r"backing off ([\d.]+)s", line)
            rows.append({"docker_timestamp": stamp,
                         "stated_delay_s": float(match.group(1)) if match else None,
                         "line": line[-240:]})
    return rows


def timestamps_ok(line: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T", line))


def intervals(rows: list[dict]) -> list[float]:
    """Actual seconds between consecutive warnings, from docker's timestamps."""
    times = []
    for row in rows:
        stamp = row.get("docker_timestamp")
        if not stamp:
            continue
        try:
            times.append(dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")))
        except ValueError:
            continue
    return [round((b - a).total_seconds(), 2) for a, b in zip(times, times[1:])]


def wait_log(name: str, needle: str, timeout: float, exclude: str = "") -> dict | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        for line in logs(name):
            if needle in line and (not exclude or exclude not in line):
                return {"after_s": round(time.monotonic() - t0, 2), "line": line[-260:]}
        time.sleep(0.5)
    return None


def stop(name: str, grace: int) -> dict:
    t0 = time.monotonic()
    rc, out = docker("stop", "-t", str(grace), name, timeout=grace + 90)
    return {"docker_stop_rc": rc, "stop_wall_s": round(time.monotonic() - t0, 2),
            "grace_requested_s": grace, **inspect_all(name), "stop_output": out[:200]}


def redis_up() -> None:
    docker("start", REDIS_CONTAINER)
    for _ in range(40):
        if redis_cli("ping") == "PONG":
            return
        time.sleep(0.5)


def redis_down(seconds_idle: float = 0.0) -> None:
    docker("stop", "-t", "1", REDIS_CONTAINER)
    if seconds_idle:
        time.sleep(seconds_idle)


def wait_job(job_id: str, states: tuple[str, ...], timeout: float) -> dict | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        row = job_states().get(job_id)
        if row and row["status"] in states:
            return {"after_s": round(time.monotonic() - t0, 2), **row}
        time.sleep(1)
    return None


# ---------------------------------------------------------------------------
# F2 cases
# ---------------------------------------------------------------------------


def summary(name: str) -> dict:
    """Everything the task demands per case, read back rather than assumed."""
    rows = warnings(name)
    return {"container_facts": inspect_all(name),
            "outage_warnings": rows,
            "warning_count": len(rows),
            "stated_backoff_delays_s": [r["stated_delay_s"] for r in rows],
            "measured_intervals_between_warnings_s": intervals(rows),
            "worker_log_tail": [line[-200:] for line in logs(name)][-12:]}


def case_c1_outage_before_start() -> dict:
    name = f"{RUN_ID}_f2_c1"
    redis_up()
    clear_lists()
    fixtures = [fixture(240) for _ in range(3)]
    for fx in fixtures:
        enqueue(fx["job_id"])
    queued = lists()
    log(f"C1 queued {queued} then stopping redis")
    redis_down()
    worker = start_worker(name)
    first = wait_log(name, WARN, 150)
    time.sleep(12)
    early = warnings(name)
    redis_up()
    recovery = wait_log(name, "reachable again", 180)
    finals = {fx["job_id"]: wait_job(fx["job_id"], ("completed", "failed"), 300)
              for fx in fixtures}
    result = {"case": "C1 Redis down before the worker starts, 3 jobs already queued",
              "worker_container": worker, "queue_before_stop": queued,
              "first_outage_warning": first,
              "warnings_before_restore": len(early),
              "stated_delays_before_restore_s": [r["stated_delay_s"] for r in early],
              "recovery_log_line": recovery,
              "jobs_final": finals,
              "jobs_completed": sum(1 for v in finals.values()
                                    if v and v["status"] == "completed"),
              "lists_after": lists(), "stop": stop(name, 60), **summary(name)}
    docker("rm", "-f", name)
    clear_lists()
    return result


def case_c2_disconnect_while_idle() -> dict:
    name = f"{RUN_ID}_f2_c2"
    redis_up()
    clear_lists()
    worker = start_worker(name)
    started = wait_log(name, "analysis worker started", 90)
    time.sleep(3)  # parked in the blocked dequeue
    redis_down()
    first = wait_log(name, WARN, 90)
    time.sleep(6)
    redis_up()
    recovery = wait_log(name, "reachable again", 180)
    # the surviving proof is work flowing, not a log line
    fx = fixture(240)
    enqueue(fx["job_id"])
    done = wait_job(fx["job_id"], ("completed", "failed"), 300)
    result = {"case": "C2 Redis lost while the worker is parked in BRPOPLPUSH",
              "worker_container": worker, "startup_log": started,
              "first_outage_warning": first, "recovery_log_line": recovery,
              "job_after_recovery": done, "lists_after": lists(),
              "stop": stop(name, 60), **summary(name)}
    docker("rm", "-f", name)
    clear_lists()
    return result


def case_c3_outage_during_job() -> dict:
    name = f"{RUN_ID}_f2_c3"
    redis_up()
    clear_lists()
    fx = fixture(size_px=6000)
    enqueue(fx["job_id"])
    worker = start_worker(name)
    picked = wait_job(fx["job_id"], ("running",), 180)
    log(f"C3 job running after {picked}")
    redis_down()
    completed_while_down = wait_job(fx["job_id"], ("completed", "failed"), 300)
    redis_state = docker("inspect", "-f", "{{.State.Status}}", REDIS_CONTAINER)[1]
    time.sleep(8)
    redis_up()
    recovery = wait_log(name, "reachable again", 240)
    drained = None
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if lists() == {"queue": "0", "processing": "0"}:
            drained = round(120 - (deadline - time.monotonic()), 2)
            break
        time.sleep(2)
    result = {"case": "C3 Redis lost while a job is in flight (commit-before-ack)",
              "worker_container": worker, "fixture": fx, "picked_up": picked,
              "job_state_when_redis_down": completed_while_down,
              "redis_state_at_that_moment": redis_state,
              "recovery_log_line": recovery,
              "lists_drained_after_recovery_s": drained,
              "final_job_state": job_states().get(fx["job_id"]),
              "lists_after": lists(), "stop": stop(name, 60), **summary(name)}
    docker("rm", "-f", name)
    clear_lists()
    return result


def case_c4_repeated_outages() -> dict:
    name = f"{RUN_ID}_f2_c4"
    redis_up()
    clear_lists()
    worker = start_worker(name, ANALYSIS_RETRY_BACKOFF_BASE_SECONDS="5",
                          ANALYSIS_RETRY_BACKOFF_MAX_SECONDS="20")
    cycles = []
    for index in range(3):
        redis_down()
        time.sleep(22)
        redis_up()
        rec = wait_log(name, "reachable again", 180)
        cycles.append({"cycle": index + 1, "outage_length_s": 22,
                       "recovery_after_restore_s": (rec or {}).get("after_s"),
                       "warning_count_so_far": len(warnings(name))})
        time.sleep(3)
    alive = inspect_all(name)
    result = {"case": "C4 three outage/restore cycles, bounded backoff, worker must not exit",
              "worker_container": worker,
              "configured": {"backoff_base_s": 5, "backoff_max_s": 20},
              "cycles": cycles, "still_running_before_stop": alive["state"],
              "restart_count_before_stop": alive["restart_count"],
              "stop": stop(name, 60), **summary(name)}
    docker("rm", "-f", name)
    clear_lists()
    return result


def case_c5_sigterm_during_backoff() -> dict:
    name = f"{RUN_ID}_f2_c5"
    worker = start_worker(name, REDIS_URL="redis://redis:6399/0",
                          ANALYSIS_RETRY_BACKOFF_BASE_SECONDS="40",
                          ANALYSIS_RETRY_BACKOFF_MAX_SECONDS="60")
    hit = wait_log(name, WARN, 120)
    match = re.search(r"backing off ([\d.]+)s", (hit or {}).get("line", ""))
    time.sleep(3)
    result = {"case": "C5 SIGTERM during a 40s retry backoff wait (closed Redis port)",
              "worker_container": worker, "first_warning": hit,
              "stated_delay_s": float(match.group(1)) if match else None,
              "stop": stop(name, 120), **summary(name)}
    docker("rm", "-f", name)
    return result


def case_sigterm_blocked(block: int) -> dict:
    name = f"{RUN_ID}_f2_cblock{block}"
    redis_up()
    clear_lists()
    worker = start_worker(name, ANALYSIS_DEQUEUE_BLOCK_SECONDS=str(block))
    wait_log(name, "analysis worker started", 90)
    time.sleep(2)
    result = {"case": f"SIGTERM during a blocked dequeue (block={block}s)",
              "worker_container": worker,
              "configured": {"dequeue_block_s": block, "socket_timeout_s": 30,
                             "shutdown_poll_s": 0.5},
              "stop": stop(name, block + 60), **summary(name)}
    docker("rm", "-f", name)
    return result


def case_c8_sigterm_during_job() -> dict:
    name = f"{RUN_ID}_f2_c8"
    redis_up()
    clear_lists()
    fx = fixture(size_px=6000)
    enqueue(fx["job_id"])
    worker = start_worker(name)
    picked = wait_job(fx["job_id"], ("running",), 180)
    state_at_signal = job_states().get(fx["job_id"])
    stop_facts = stop(name, 240)
    result = {"case": "C8 SIGTERM while a job is running (in-flight completes first)",
              "worker_container": worker, "fixture": fx, "picked_up": picked,
              "job_state_at_signal": state_at_signal,
              "job_state_after_stop": job_states().get(fx["job_id"]),
              "lists_after_stop": lists(), "stop": stop_facts, **summary(name)}
    docker("rm", "-f", name)
    clear_lists()
    return result


def case_c9_idle_recovery_counter() -> dict:
    """Does an idle worker ever learn that Redis came back?

    The queue is kept empty for the whole case, so after an outage the only
    successful Redis call is a blocking dequeue that returns no message. In
    ``run_worker`` both the recovery log line and the reset of the
    consecutive-failure counter sit *after* that path's ``continue``
    (backend/workers/analysis_worker.py:347-366). The prediction this case
    tests is therefore twofold: no recovery line while idle, and a backoff
    sequence that keeps growing across outages because the counter is never
    cleared. The final enqueue shows when the line is allowed to appear.
    """
    name = f"{RUN_ID}_f2_c9"
    redis_up()
    clear_lists()
    worker = start_worker(name, ANALYSIS_RETRY_BACKOFF_BASE_SECONDS="5",
                          ANALYSIS_RETRY_BACKOFF_MAX_SECONDS="600",
                          ANALYSIS_DEQUEUE_BLOCK_SECONDS="1")
    started = wait_log(name, "analysis worker started", 90)
    cycles = []
    for index in range(3):
        before = len(warnings(name))
        redis_down()
        time.sleep(30)   # long enough for at least one backoff to be entered
        redis_up()
        time.sleep(45)   # many idle polls succeed with nothing queued
        rows = warnings(name)
        cycles.append({
            "cycle": index + 1,
            "outage_length_s": 30,
            "idle_period_after_restore_s": 45,
            "warnings_this_cycle": rows[before:],
            "all_stated_delays_s": [r["stated_delay_s"] for r in rows],
            "measured_intervals_s": intervals(rows),
            "warning_count_total": len(rows),
        })
        log(f"c9 cycle {index+1} stated delays="
            f"{[r['stated_delay_s'] for r in rows]}")
    lines = logs(name)
    recovery_while_idle = [l for l in lines if "reachable again" in l]
    fx = fixture(240)
    enqueue(fx["job_id"])
    done = wait_job(fx["job_id"], ("completed", "failed"), 240)
    after_job = [l for l in logs(name) if "reachable again" in l]
    result = {
        "case": "C3b Redis outage/restore cycles with an empty queue "
                "(recovery observability and failure-counter reset)",
        "worker_container": worker, "startup_log": started,
        "configured": {"backoff_base_s": 5, "backoff_max_s": 600,
                       "dequeue_block_s": 1},
        "cycles": cycles,
        "recovery_lines_logged_while_idle": recovery_while_idle,
        "job_enqueued_after_cycles": done,
        "recovery_lines_after_first_processed_job": after_job,
        "final_lists": lists(), "stop": stop(name, 60), **summary(name),
    }
    docker("rm", "-f", name)
    clear_lists()
    return result


CASES = {
    "c1": case_c1_outage_before_start,
    "c2": case_c2_disconnect_while_idle,
    "c3": case_c3_outage_during_job,
    "c4": case_c4_repeated_outages,
    "c5": case_c5_sigterm_during_backoff,
    "c6": lambda: case_sigterm_blocked(20),
    "c7": lambda: case_sigterm_blocked(1),
    "c8": case_c8_sigterm_during_job,
    "c9": case_c9_idle_recovery_counter,
}


def main() -> int:
    EVIDENCE.mkdir(exist_ok=True)
    which = sys.argv[1:] or ["all"]
    keys = list(CASES) if which == ["all"] else which
    for key in keys:
        if key not in CASES:
            log(f"unknown case {key}; have {sorted(CASES)}")
            return 2
    log(f"running F2 cases: {keys}")
    for key in keys:
        t0 = time.monotonic()
        try:
            payload = CASES[key]()
        except Exception as error:  # a failed case is evidence, not a silent skip
            payload = {"case": key, "harness_error": f"{type(error).__name__}: {error}"}
            log(f"{key} ERRORED {type(error).__name__}: {error}")
        payload["wall_s"] = round(time.monotonic() - t0, 1)
        payload["database_identities_at_case_end"] = worker_identities()
        record(f"f2_{key}", payload)
        log(f"{key} done in {payload['wall_s']}s")
    redis_up()
    return 0


if __name__ == "__main__":
    sys.exit(main())
