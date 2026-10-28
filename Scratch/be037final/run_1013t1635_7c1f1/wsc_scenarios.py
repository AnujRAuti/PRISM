"""BE-037 WS-C: outage scenarios run against THIS RUN's isolated Redis.

Usage:  python wsc_scenarios.py <scenario> [--long]

Every scenario drives the real worker module as its own OS process (so signals,
socket behaviour and logging are the production ones) against the disposable
stack named be037fin7c1f1, and writes measured evidence to evidence/<id>.json.

Nothing here touches pofa_db / pofa_redis / pofa_minio / pofa_dev / pofa_test:
Redis is reached on host port 16379 (this run's container), PostgreSQL on 15432,
MinIO on 19000, all created from this run's compose file.

Credentials are this run's throwaway values. They are never written into the
evidence files: only the *key names* are recorded.

ML note: HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE are forced on so the embedding path
takes its documented "unavailable" branch instead of downloading model weights,
which this task forbids.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
sys.path.insert(0, str(REPO))
PY = str(REPO / "backend/.venv312_repro/Scripts/python.exe")
RUN_ID = "be037fin7c1f1"
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"

REDIS_CONTAINER = f"{RUN_ID}_redis"
NETWORK = f"{RUN_ID}_net"

# Throwaway, disposable-only connection strings.
DB_URL = (
    f"postgresql+psycopg2://postgres:{RUN_ID}pw@localhost:15432/{RUN_ID}_app"
)
REDIS_URL = f"redis://127.0.0.1:16379/0"
S3_ENDPOINT = "http://127.0.0.1:19000"
S3_KEY = f"{RUN_ID}admin"
S3_SECRET = f"{RUN_ID}secret"

# Timing bounds used by the host-process scenarios. socket_timeout (8) is kept
# above the blocking dequeue's own wait (3) as the queue's invariant requires;
# the values are small so a whole scenario fits a finite timeout, and each
# measurement reports the configured value next to the observed one.
BASE_ENV = {
    "DATABASE_URL": DB_URL,
    "REDIS_URL": REDIS_URL,
    "ENVIRONMENT": "development",
    "S3_ENDPOINT": S3_ENDPOINT,
    "S3_ACCESS_KEY": S3_KEY,
    "S3_SECRET_KEY": S3_SECRET,
    "S3_USE_SSL": "false",
    "S3_QUARANTINE_BUCKET": f"{RUN_ID}-quarantine",
    "S3_EVIDENCE_BUCKET": f"{RUN_ID}-evidence",
    "ANALYSIS_QUEUE_NAME": f"{RUN_ID}:analysis:jobs",
    "ANALYSIS_REDIS_SOCKET_TIMEOUT_SECONDS": "8",
    "ANALYSIS_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS": "3",
    "ANALYSIS_REDIS_HEALTH_CHECK_INTERVAL_SECONDS": "2",
    "ANALYSIS_DEQUEUE_BLOCK_SECONDS": "3",
    "ANALYSIS_RETRY_BACKOFF_BASE_SECONDS": "4",
    "ANALYSIS_RETRY_BACKOFF_MAX_SECONDS": "20",
    "ANALYSIS_SHUTDOWN_POLL_SECONDS": "0.5",
    "ANALYSIS_ABANDONED_TIMEOUT_SECONDS": "30",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}

BACKOFF_RE = re.compile(
    r"redis unavailable; backing off ([\d.]+)s \(consecutive failures (\d+)\)"
)
RECOVERED_RE = re.compile(r"analysis worker recovered (\d+) abandoned")
AGAIN_RE = re.compile(r"redis reachable again after (\d+) backoff")

# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def docker(*args: str, timeout: int = 90) -> tuple[int, str]:
    proc = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def redis_state() -> str:
    rc, out = docker("inspect", "-f", "{{.State.Status}}", REDIS_CONTAINER)
    return out if rc == 0 else f"inspect-failed:{out}"


def redis_down() -> None:
    rc, out = docker("stop", "-t", "1", REDIS_CONTAINER)
    log(f"redis stop rc={rc} state={redis_state()}")


def redis_up() -> None:
    rc, out = docker("start", REDIS_CONTAINER)
    log(f"redis start rc={rc} state={redis_state()}")


def redis_freeze() -> None:
    rc, _ = docker("pause", REDIS_CONTAINER)
    log(f"redis pause rc={rc} state={redis_state()}")


def redis_thaw() -> None:
    rc, _ = docker("unpause", REDIS_CONTAINER)
    log(f"redis unpause rc={rc} state={redis_state()}")


class Harness:
    """A redis client with a short deadline, so the harness itself never hangs.

    Must not be used while Redis is paused (the call would time out); every
    measurement during a freeze is taken from the worker's own log instead.
    """

    def __init__(self) -> None:
        import redis

        self.r = redis.Redis(
            host="127.0.0.1",
            port=16379,
            socket_timeout=2,
            socket_connect_timeout=2,
            decode_responses=True,
        )

    def llen(self, key: str) -> int:
        return int(self.r.llen(key))

    def lists(self, queue: str) -> dict:
        return {"main": self.llen(queue), "processing": self.llen(f"{queue}:processing")}

    def enqueue(self, queue: str, job_id: str) -> None:
        self.r.rpush(queue, json.dumps({"job_id": job_id}, separators=(",", ":")))

    def push_raw(self, queue: str, payload: str) -> None:
        self.r.rpush(queue, payload)

    def contents(self, queue: str) -> dict:
        return {
            "main": list(self.r.lrange(queue, 0, -1)),
            "processing": list(self.r.lrange(f"{queue}:processing", 0, -1)),
        }

    def set_key(self, key: str, value: str) -> None:
        self.r.set(key, value)

    def ping(self) -> bool:
        try:
            return bool(self.r.ping())
        except Exception:
            return False


class Worker:
    """The real worker module as a subprocess, with arrival-stamped logs."""

    def __init__(self, name: str, env_overrides: dict | None = None) -> None:
        self.name = name
        # BASE_ENV is an overlay, not a whole environment: a child launched
        # without SystemRoot/PATH cannot initialise Winsock at all.
        self.env = dict(os.environ)
        self.env.update(BASE_ENV)
        self.env.update({k: str(v) for k, v in (env_overrides or {}).items()})
        self.queue = self.env["ANALYSIS_QUEUE_NAME"]
        self.lines: list[tuple[float, str]] = []
        self._t0 = time.monotonic()
        self._stop = False
        self.log_path = EVIDENCE / f"{name}.log"
        self.process: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        EVIDENCE.mkdir(exist_ok=True)
        self.process = subprocess.Popen(
            [PY, "-u", "-m", "backend.workers.analysis_worker"],
            cwd=str(REPO),
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()
        log(f"worker {self.name} pid={self.process.pid}")

    def _pump(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        with open(self.log_path, "w", encoding="utf-8") as fh:
            for line in self.process.stdout:
                stamp = time.monotonic() - self._t0
                self.lines.append((stamp, line.rstrip()))
                fh.write(f"[+{stamp:7.2f}s] {line.rstrip()}\n")
                fh.flush()

    def mark(self) -> float:
        return time.monotonic() - self._t0

    def text(self) -> str:
        return "\n".join(m for _, m in self.lines)

    def find(self, pattern: str) -> list[tuple[float, str]]:
        rx = re.compile(pattern)
        return [(t, m) for t, m in self.lines if rx.search(m)]

    def wait_for(self, pattern: str, timeout: float) -> tuple[float, str] | None:
        rx = re.compile(pattern)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for t, m in self.lines:
                if rx.search(m):
                    return t, m
            if not self.alive():
                return None
            time.sleep(0.1)
        return None

    def wait_count(self, pattern: str, count: int, timeout: float) -> list:
        rx = re.compile(pattern)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            hits = self.find(pattern)
            if len(hits) >= count:
                return [(round(t, 2), m) for t, m in hits[:count]]
            time.sleep(0.2)
        return [(round(t, 2), m) for t, m in self.find(pattern)]

    def backoffs(self) -> list[dict]:
        out = []
        for t, m in self.lines:
            match = BACKOFF_RE.search(m)
            if match:
                out.append(
                    {
                        "arrival_s": round(t, 2),
                        "stated_delay_s": float(match.group(1)),
                        "stated_consecutive_failures": int(match.group(2)),
                    }
                )
        return out

    def alive(self) -> bool:
        assert self.process is not None
        return self.process.poll() is None

    def wait_exit(self, timeout: float) -> int | None:
        assert self.process is not None
        try:
            return self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def kill(self) -> None:
        if self.alive():
            assert self.process is not None
            self.process.kill()
            self.process.wait(timeout=15)

    def state_summary(self) -> dict:
        assert self.process is not None
        return {
            "pid": self.process.pid,
            "exit_code": self.process.returncode,
            "alive_at_measurement": self.process.poll() is None,
            "log_lines": len(self.lines),
            "backoff_warnings": self.backoffs(),
            "recovery_lines": [
                {"arrival_s": round(t, 2), "message": m} for t, m in self.find(RECOVERED_RE.pattern)
            ],
            "again_lines": [
                {"arrival_s": round(t, 2), "message": m} for t, m in self.find(AGAIN_RE.pattern)
            ],
        }


# ---------------------------------------------------------------------------
# fixtures (disposable DB / disposable MinIO only)
# ---------------------------------------------------------------------------


def _app_env() -> None:
    for key, value in BASE_ENV.items():
        import os

        os.environ[key] = value


def fixture_evidence_and_job(size_px: int = 240) -> dict:
    """Store a real synthetic object in disposable MinIO and queue a job for it.

    Returns {evidence_id, job_id, bytes}.
    """
    import io

    from PIL import Image

    _app_env()
    from backend.services.storage import StorageService

    evidence_id = str(uuid.uuid4())
    rng = __import__("random").Random(evidence_id)
    img = Image.new("RGB", (size_px, size_px))
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(size_px * size_px)])
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
        db.add(
            Evidence(
                id=evidence_id,
                filename=f"{evidence_id}.jpg",
                content_type="image/jpeg",
                storage_key=key,
                file_size=len(data),
                status="uploaded_quarantine",
            )
        )
        job = AnalysisJob(evidence_id=evidence_id, status="queued")
        db.add(job)
        db.commit()
        job_id = str(job.id)
    finally:
        db.close()
    return {"evidence_id": evidence_id, "job_id": job_id, "bytes": len(data), "storage_key": key}


def job_states(prefix: str = "") -> dict:
    """Per-job status for the fixture jobs created by this scenario."""
    import os

    _app_env()
    from sqlalchemy import create_engine, text

    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "select j.id, j.status, j.attempt_count, j.error, "
                "(select count(*) from analysis_results r where r.job_id = j.id) as results "
                "from analysis_jobs j order by j.created_at"
            )
        ).mappings().all()
    states = {
        str(r["id"]): {
            "status": r["status"],
            "attempt_count": r["attempt_count"],
            "error": r["error"],
            "result_rows": r["results"],
        }
        for r in rows
    }
    return states


def reset_lists(queue: str) -> None:
    h = Harness()
    h.r.delete(queue, f"{queue}:processing")


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------


def scenario(name: str, env: dict | None = None) -> Worker:
    w = Worker(name, env)
    w.start()
    return w


def record(name: str, payload: dict) -> None:
    EVIDENCE.mkdir(exist_ok=True)
    path = EVIDENCE / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    log(f"wrote {path.relative_to(HERE)}")


def sc1_startup_outage() -> None:
    """Redis already unavailable when the worker starts."""
    h = Harness()
    reset_lists(BASE_ENV["ANALYSIS_QUEUE_NAME"])
    if redis_state() == "running":
        redis_down()
    time.sleep(1)
    w = scenario("sc1_startup_outage")
    w.wait_for("redis unavailable", timeout=40)
    time.sleep(14)
    during = w.state_summary()
    ping_during = h.ping()
    redis_up()
    fx = fixture_evidence_and_job()
    h.enqueue(BASE_ENV["ANALYSIS_QUEUE_NAME"], fx["job_id"])
    done = w.wait_for("analysis job completed", timeout=300)
    time.sleep(1)
    payload = {
        "scenario": "S1 unavailable-before-startup",
        "configured": {
            "base_s": 4.0,
            "max_s": 20.0,
            "block_s": 3,
            "socket_timeout_s": 8.0,
        },
        "worker_during_outage": during,
        "harness_ping_during_outage": ping_during,
        "fixture": fx,
        "completed_log_entry": done,
        "lists_after": h.lists(BASE_ENV["ANALYSIS_QUEUE_NAME"]) if h.ping() else "redis-unreachable",
        "job_states": {fx["job_id"]: job_states().get(fx["job_id"], "missing")},
        "worker_final": w.state_summary(),
    }
    w.kill()
    record("sc1_startup_outage", payload)


def sc2_disconnect_during_blocked_dequeue() -> None:
    """A clean disconnect while the worker is parked in the blocking dequeue."""
    q = BASE_ENV["ANALYSIS_QUEUE_NAME"]
    if redis_state() != "running":
        redis_up()
    h = Harness()
    reset_lists(q)
    w = scenario("sc2_disconnect_during_blocked_dequeue")
    w.wait_for("analysis worker started", timeout=30)
    t_stop = time.monotonic() - w._t0
    redis_down()
    hit = w.wait_for("redis unavailable", timeout=45)
    measured = None
    if hit:
        measured = round(hit[0] - t_stop, 2)
    time.sleep(3)
    still = w.alive()
    redis_up()
    fx = fixture_evidence_and_job()
    h.enqueue(q, fx["job_id"])
    done = w.wait_for("analysis job completed", timeout=300)
    payload = {
        "scenario": "S2 disconnect during blocking dequeue",
        "stop_at_worker_clock_s": round(t_stop, 2),
        "first_backoff_warning": hit,
        "seconds_stop_to_warning": measured,
        "worker_alive_during_outage": still,
        "configured_socket_timeout_s": 8.0,
        "configured_block_s": 3,
        "fixture": fx,
        "completed_log_entry": done,
        "lists_after": h.lists(q),
        "job_states": {fx["job_id"]: job_states().get(fx["job_id"], "missing")},
        "worker_final": w.state_summary(),
    }
    w.kill()
    record("sc2_disconnect_during_blocked_dequeue", payload)


def sc3_stall_during_ack() -> None:
    """Redis freezes while the job runs, and stays frozen across the ack.

    The DB outcome commits before the acknowledgement, so the observable
    signature of a frozen ack is: the job row reaches ``completed`` while the
    payload is still in the processing list and the completion log line has not
    been printed.

    The freeze is held past TWO socket deadlines on purpose, because the first
    one alone does not end the outage. ``process_message`` catches the failed
    ack in its own ``except Exception`` and tries to requeue the message, which
    is a second Redis command that needs its own timeout. The measured path
    therefore is: ack raises after ``socket_timeout`` -> the row is set back to
    ``queued`` (committed) -> the retry requeue raises -> ``run_worker``'s
    transient handler backs off. After the thaw the recovery pass must see a
    ``queued`` job with its payload still in the processing list, requeue it
    (counted, never discarded), reprocess it to ``completed``, acknowledge it and
    log "redis reachable again".

    The freeze is placed from the database's own state, not from a stopwatch: a
    fixed sleep landed it on the worker's startup recovery instead, which is a
    different scenario (that one is sc4).
    """
    q = BASE_ENV["ANALYSIS_QUEUE_NAME"]
    if redis_state() != "running":
        redis_up()
    h = Harness()
    reset_lists(q)
    fx = fixture_evidence_and_job()
    h.enqueue(q, fx["job_id"])
    w = scenario("sc3_stall_during_ack")

    def wait_status(wanted: str, timeout: float) -> float | None:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            state = job_states().get(fx["job_id"], {})
            if state.get("status") == wanted:
                return round(time.monotonic() - w._t0, 2)
            time.sleep(1)
        return None

    running_at = wait_status("running", 120)
    frozen_at = w.mark()
    redis_freeze()
    committed_at = wait_status("completed", 180)
    # socket_timeout in this harness is 8s. Hold 20s past the commit so the ack
    # AND the retry requeue have each certainly raised on their own deadline.
    time.sleep(20)
    warnings = w.find("redis unavailable")
    payload = {
        "scenario": "S3 stall without a clean disconnect, across the acknowledgement",
        "configured_socket_timeout_s": 8.0,
        "job_running_at_worker_clock_s": running_at,
        "frozen_at_worker_clock_s": frozen_at,
        "db_committed_while_frozen_at_worker_clock_s": committed_at,
        "held_frozen_past_commit_s": 20,
        "worker_alive_while_frozen": w.alive(),
    }
    thaw_at = w.mark()
    redis_thaw()
    again = w.wait_for("redis reachable again", timeout=120)
    time.sleep(3)
    payload["thaw_at_worker_clock_s"] = thaw_at
    payload["ack_outage_warnings"] = warnings
    payload["again_log_entry"] = again
    payload["recovery_lines"] = w.find(RECOVERED_RE.pattern)
    payload["contents_after"] = h.contents(q)
    payload["completion_lines"] = w.find("analysis job completed")
    states = job_states()
    payload["job_state_after"] = states.get(fx["job_id"], "missing")
    payload["final_lists"] = h.lists(q)
    payload["worker_final"] = w.state_summary()
    payload["fixture"] = fx
    w.kill()
    record("sc3_stall_during_ack", payload)


def sc4_blackhole_during_idle_dequeue() -> None:
    """The pre-fix fatal case: a frozen Redis while the worker is idle-polling."""
    q = BASE_ENV["ANALYSIS_QUEUE_NAME"]
    if redis_state() != "running":
        redis_up()
    h = Harness()
    reset_lists(q)
    w = scenario("sc4_blackhole_during_idle_dequeue")
    w.wait_for("analysis worker started", timeout=30)
    t_freeze = w.mark()
    redis_freeze()
    hit = w.wait_for("redis unavailable", timeout=60)
    seconds = round(hit[0] - t_freeze, 2) if hit else None
    time.sleep(3)
    alive = w.alive()
    redis_thaw()
    time.sleep(2)
    fx = fixture_evidence_and_job()
    h.enqueue(q, fx["job_id"])
    done = w.wait_for("analysis job completed", timeout=300)
    payload = {
        "scenario": "S4 blackhole during the idle blocking dequeue",
        "configured_socket_timeout_s": 8.0,
        "configured_block_s": 3,
        "freeze_at_worker_clock_s": round(t_freeze, 2),
        "first_backoff_warning": hit,
        "seconds_freeze_to_warning": seconds,
        "pre_fix_baseline_reference": "final-07-wsc-baseline-frozen-redis.json (45s budget exhausted, no reply)",
        "worker_alive_after_warning": alive,
        "fixture": fx,
        "completed_log_entry": done,
        "lists_after": h.lists(q),
        "job_states": {fx["job_id"]: job_states().get(fx["job_id"], "missing")},
        "worker_final": w.state_summary(),
    }
    w.kill()
    record("sc4_blackhole_during_idle_dequeue", payload)


def sc5_restore_with_queued_jobs() -> None:
    """Work already in Redis when the worker starts into an outage."""
    q = BASE_ENV["ANALYSIS_QUEUE_NAME"]
    if redis_state() != "running":
        redis_up()
    h = Harness()
    reset_lists(q)
    fixtures = [fixture_evidence_and_job() for _ in range(3)]
    for fx in fixtures:
        h.enqueue(q, fx["job_id"])
    before = h.lists(q)
    redis_down()
    w = scenario("sc5_restore_with_queued_jobs")
    time.sleep(8)
    during = w.state_summary()
    redis_up()
    restored_at = w.mark()
    completions = w.wait_count("analysis job completed", 3, timeout=420)
    time.sleep(2)
    states = job_states()
    payload = {
        "scenario": "S5 restoration with queued jobs (survives via Redis AOF)",
        "lists_before_outage": before,
        "worker_during_outage": during,
        "redis_restored_at_worker_clock_s": round(restored_at, 2),
        "fixtures": fixtures,
        "completion_lines": [
            {"arrival_s": t, "message": m} for t, m in completions
        ],
        "lists_after": h.lists(q),
        "job_states": {fx["job_id"]: states.get(fx["job_id"], "missing") for fx in fixtures},
        "worker_final": w.state_summary(),
    }
    w.kill()
    record("sc5_restore_with_queued_jobs", payload)


def sc6_repeated_outages() -> None:
    """Several stop/start cycles: bounded waits, no tight loop, no exit."""
    q = BASE_ENV["ANALYSIS_QUEUE_NAME"]
    if redis_state() != "running":
        redis_up()
    h = Harness()
    reset_lists(q)
    w = scenario("sc6_repeated_outages")
    w.wait_for("analysis worker started", timeout=30)
    cycles = []
    for i in range(4):
        redis_down()
        time.sleep(18)
        cycles.append(
            {
                "cycle": i + 1,
                "warnings_during_cycle": len(w.backoffs()),
                "alive": w.alive(),
            }
        )
        redis_up()
        time.sleep(6)
    fx = fixture_evidence_and_job()
    h.enqueue(q, fx["job_id"])
    done = w.wait_for("analysis job completed", timeout=300)
    warnings = w.backoffs()
    inter_arrivals = [
        round(warnings[i]["arrival_s"] - warnings[i - 1]["arrival_s"], 2)
        for i in range(1, len(warnings))
    ]
    payload = {
        "scenario": "S6 repeated outages",
        "configured_base_s": 4.0,
        "configured_max_s": 20.0,
        "cycles": cycles,
        "total_warnings": len(warnings),
        "stated_delays_s": [x["stated_delay_s"] for x in warnings],
        "stated_consecutive_failures": [x["stated_consecutive_failures"] for x in warnings],
        "measured_inter_warning_intervals_s": inter_arrivals,
        "max_stated_delay_s": max((x["stated_delay_s"] for x in warnings), default=None),
        "again_lines": w.find(AGAIN_RE.pattern),
        "worker_ever_exited": not w.alive(),
        "fixture": fx,
        "completed_log_entry": done,
        "lists_after": h.lists(q),
        "job_states": {fx["job_id"]: job_states().get(fx["job_id"], "missing")},
        "worker_final": w.state_summary(),
    }
    w.kill()
    record("sc6_repeated_outages", payload)


def sc7_unrelated_redis_error_propagates() -> None:
    """A WRONGTYPE reply is not an outage: it must propagate and exit."""
    q = f"{RUN_ID}:analysis:stringkey"
    if redis_state() != "running":
        redis_up()
    h = Harness()
    h.r.delete(q, f"{q}:processing")
    h.set_key(q, "not-a-list")
    w = Worker("sc7_unrelated_redis_error", {"ANALYSIS_QUEUE_NAME": q})
    w.start()
    exit_code = w.wait_exit(45)
    time.sleep(1)
    text = w.text()
    payload = {
        "scenario": "S7 unrelated Redis command error propagates",
        "setup": "ANALYSIS_QUEUE_NAME points at a key holding a Redis string",
        "exit_code": exit_code,
        "alive": w.alive(),
        "backoff_warnings_emitted": len(w.backoffs()),
        "traceback_present": "ResponseError" in text,
        "wrongtype_present": "WRONGTYPE" in text,
        "tail": text.splitlines()[-12:],
    }
    h.r.delete(q, f"{q}:processing")
    record("sc7_unrelated_redis_error", payload)


def sc8_invalid_payload_is_visible() -> None:
    """Observation: a malformed payload is a ValueError, not an outage."""
    q = BASE_ENV["ANALYSIS_QUEUE_NAME"]
    if redis_state() != "running":
        redis_up()
    h = Harness()
    reset_lists(q)
    h.push_raw(q, '{"not_job_id":1}')
    w = scenario("sc8_invalid_payload")
    exit_code = w.wait_exit(45)
    time.sleep(1)
    text = w.text()
    payload = {
        "scenario": "S8 malformed queue payload (observation of mandated propagation)",
        "exit_code": exit_code,
        "backoff_warnings_emitted": len(w.backoffs()),
        "valueerror_present": "Invalid analysis queue payload" in text,
        "lists_after": h.lists(q),
        "contents_after": h.contents(q),
        "tail": text.splitlines()[-12:],
    }
    reset_lists(q)
    record("sc8_invalid_payload", payload)


def smoke() -> None:
    """Harness self-test: fixture -> queue -> real worker -> completed row."""
    q = BASE_ENV["ANALYSIS_QUEUE_NAME"]
    if redis_state() != "running":
        redis_up()
    h = Harness()
    reset_lists(q)
    fx = fixture_evidence_and_job()
    h.enqueue(q, fx["job_id"])
    w = scenario("smoke")
    done = w.wait_for("analysis job completed", timeout=300)
    time.sleep(1)
    payload = {
        "scenario": "smoke",
        "fixture": fx,
        "completed_log_entry": done,
        "lists_after": h.lists(q),
        "job_states": {fx["job_id"]: job_states().get(fx["job_id"], "missing")},
        "worker_final": w.state_summary(),
        "full_log": w.text(),
    }
    w.kill()
    record("smoke", payload)


DEBUG_COMMAND = (
    "import logging; logging.basicConfig(level=logging.DEBUG); "
    "from backend.workers.analysis_worker import install_shutdown_handlers, run_worker; "
    "install_shutdown_handlers(); run_worker()"
)


def _fixture_with_reprocessing() -> dict:
    """An unlinked job and a job delegated by a real PENDING reprocessing request."""
    import os

    _app_env()
    from sqlalchemy.orm import sessionmaker

    from backend.db.models import ReprocessingRequest
    from backend.db.session import get_engine

    unlinked = fixture_evidence_and_job()
    linked = fixture_evidence_and_job()
    Session = sessionmaker(bind=get_engine())
    db = Session()
    try:
        req = ReprocessingRequest(
            evidence_id=linked["evidence_id"],
            requested_by=str(uuid.uuid4()),
            reason="BE-037 WS-A integration evidence",
            status="PENDING",
            analysis_job_id=linked["job_id"],
        )
        db.add(req)
        db.commit()
        linked["reprocessing_id"] = str(req.id)
    finally:
        db.close()
    return {"unlinked": unlinked, "linked": linked}


def sc9_reprocessing_hook() -> None:
    """WS-A on the real worker: an optional hook must not raise a false ERROR.

    The worker loop is the production ``run_worker``; only the root log level is
    raised to DEBUG so the documented no-op line is observable.
    """
    q = BASE_ENV["ANALYSIS_QUEUE_NAME"]
    if redis_state() != "running":
        redis_up()
    h = Harness()
    reset_lists(q)
    fx = _fixture_with_reprocessing()
    h.enqueue(q, fx["unlinked"]["job_id"])
    h.enqueue(q, fx["linked"]["job_id"])

    w = Worker("sc9_reprocessing_hook")
    w.process = subprocess.Popen(
        [PY, "-u", "-c", DEBUG_COMMAND],
        cwd=str(REPO),
        env={k: v for k, v in w.env.items()},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    w._t0 = time.monotonic()
    w.thread = threading.Thread(target=w._pump, daemon=True)
    w.thread.start()
    log(f"worker {w.name} pid={w.process.pid} (DEBUG)")

    first = w.wait_for("no reprocessing request delegates", timeout=360)
    completions = w.wait_count("analysis job completed", 2, timeout=420)
    second = completions[-1] if completions else None
    time.sleep(6)

    import os

    _app_env()
    from sqlalchemy import create_engine, text

    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        req_state = [
            {k: str(v) for k, v in dict(r).items()} for r in conn.execute(
                text(
                    "select status, completed_at from reprocessing_requests where id = :i"
                ),
                {"i": fx["linked"]["reprocessing_id"]},
            ).mappings().all()
        ]
        audit = conn.execute(
            text(
                "select count(*) as n from audit_ledger_events where event_type = "
                "'INTELLIGENCE_REPROCESS_COMPLETED'"
            )
        ).mappings().one()
        notifications = conn.execute(
            text("select count(*) as n from notifications")
        ).mappings().one()

    text_all = w.text()
    payload = {
        "scenario": "S9 reprocessing hook on the real worker (DEBUG level)",
        "unlinked": fx["unlinked"],
        "linked": fx["linked"],
        "noop_debug_line": first,
        "completion_line": second,
        "counts": {
            "noop_debug_lines": len(w.find("no reprocessing request delegates")),
            "error_lines": len(w.find(r"^ERROR|:ERROR")),
            "traceback_lines": len(w.find(r"Traceback")),
            "reprocessing_hook_failed_lines": len(w.find("reprocessing completion hook failed")),
            "linkage_lookup_failed_lines": len(w.find("linkage lookup failed")),
            "job_completed_lines": len(w.find("analysis job completed")),
        },
        "raw_error_and_debug_lines": [
            m for _, m in w.lines if "reprocessing" in m or m.startswith("ERROR")
        ][:20],
        "reprocessing_request_state": req_state,
        "audit_events_reprocess_completed": audit["n"],
        "notifications_rows": notifications["n"],
        "lists_after": h.lists(q),
        "job_states": {
            fx["unlinked"]["job_id"]: job_states().get(fx["unlinked"]["job_id"], "missing"),
            fx["linked"]["job_id"]: job_states().get(fx["linked"]["job_id"], "missing"),
        },
        "worker_final": w.state_summary(),
    }
    w.kill()
    record("sc9_reprocessing_hook", payload)


def sc10_recovery_classification_matrix() -> None:
    """Recovery of entries a dead worker left in the processing list.

    Four kinds of leftover are planted before a fresh worker starts, so its
    startup recovery pass has to classify each one under real conditions:

    - stale: ``running`` with ``started_at`` older than the abandoned timeout ->
      genuinely abandoned, must be requeued and counted.
    - fresh: ``running`` with a current ``started_at`` -> a live worker owns it,
      recovery must leave the payload in place (never steals live work).
    - terminal: ``completed`` -> must be discarded, never reprocessed.
    - corrupt / missing: a payload with no job_id and a job_id with no row ->
      discarded, and the worker's own dequeue path acknowledges them.

    The requeued job is then followed to completion, which is the real proof
    that recovery restored work instead of dropping it.
    """
    from datetime import datetime, timedelta, timezone

    q = BASE_ENV["ANALYSIS_QUEUE_NAME"]
    if redis_state() != "running":
        redis_up()
    h = Harness()
    reset_lists(q)

    stale = fixture_evidence_and_job()
    fresh = fixture_evidence_and_job()
    terminal = fixture_evidence_and_job()

    _app_env()
    from sqlalchemy import create_engine, text

    engine = create_engine(DB_URL)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text("update analysis_jobs set status='running', started_at=:t where id=:i"),
            {"t": now - timedelta(seconds=600), "i": stale["job_id"]},
        )
        conn.execute(
            text("update analysis_jobs set status='running', started_at=:t where id=:i"),
            {"t": now, "i": fresh["job_id"]},
        )
        conn.execute(
            text(
                "update analysis_jobs set status='completed', started_at=:s, "
                "completed_at=:t where id=:i"
            ),
            {"s": now - timedelta(seconds=600), "t": now, "i": terminal["job_id"]},
        )
    missing_id = str(uuid.uuid4())

    payload_json = lambda job_id: json.dumps({"job_id": job_id}, separators=(",", ":"))
    for payload in (
        payload_json(stale["job_id"]),
        payload_json(fresh["job_id"]),
        payload_json(terminal["job_id"]),
        payload_json(missing_id),
        '{"not_job_id":1}',
    ):
        h.push_raw(f"{q}:processing", payload)
    planted = h.contents(q)

    w = scenario("sc10_recovery_classification_matrix")
    recovered = w.wait_for(RECOVERED_RE.pattern, timeout=90)
    parsed = None
    if recovered:
        match = RECOVERED_RE.search(recovered[1])
        parsed = int(match.group(1)) if match else None
    after_pass = h.contents(q)
    done = w.wait_for("analysis job completed", timeout=330)
    time.sleep(2)
    final = h.contents(q)
    states = job_states()

    record("sc10_recovery_classification", {
        "scenario": "S10 recovery of abandoned processing-list entries",
        "configured_abandoned_timeout_s": 30,
        "fixtures": {"stale": stale, "fresh": fresh, "terminal": terminal, "missing_id": missing_id},
        "planted_contents": planted,
        "recovery_log_entry": recovered,
        "recovered_count_logged": parsed,
        "contents_after_recovery_pass": after_pass,
        "stale_job_completion_log": done,
        "final_contents": final,
        "classification": {
            "stale_requeued_not_lost": parsed == 1
            and payload_json(stale["job_id"])
            in (after_pass["main"] + after_pass["processing"]),
            "stale_payload_acked_at_the_end": payload_json(stale["job_id"])
            not in (final["main"] + final["processing"]),
            "fresh_left_untouched": payload_json(fresh["job_id"]) in final["processing"],
            "terminal_discarded": payload_json(terminal["job_id"]) not in final["processing"],
            "missing_discarded": payload_json(missing_id) not in final["processing"],
            "corrupt_discarded": '{"not_job_id":1}' not in final["processing"],
            "stale_job_reprocessed_to_completed": (
                states.get(stale["job_id"], {}).get("status") == "completed"
                and states.get(stale["job_id"], {}).get("result_rows") == 1
            ),
            "terminal_job_not_reprocessed": states.get(terminal["job_id"], {}).get(
                "attempt_count"
            ) == 0,
        },
        "job_states": {
            key: states.get(value["job_id"], "missing")
            for key, value in (
                ("stale", stale),
                ("fresh", fresh),
                ("terminal", terminal),
            )
        },
        "lists_after": h.lists(q),
        "worker_final": w.state_summary(),
    })
    w.kill()
    reset_lists(q)


SCENARIOS = {
    "smoke": smoke,
    "sc1": sc1_startup_outage,
    "sc2": sc2_disconnect_during_blocked_dequeue,
    "sc3": sc3_stall_during_ack,
    "sc4": sc4_blackhole_during_idle_dequeue,
    "sc5": sc5_restore_with_queued_jobs,
    "sc6": sc6_repeated_outages,
    "sc7": sc7_unrelated_redis_error_propagates,
    "sc8": sc8_invalid_payload_is_visible,
    "sc9": sc9_reprocessing_hook,
    "sc10": sc10_recovery_classification_matrix,
}


def main() -> int:
    key = sys.argv[1]
    fn = SCENARIOS[key]
    started = time.monotonic()
    fn()
    log(f"{key} finished in {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
