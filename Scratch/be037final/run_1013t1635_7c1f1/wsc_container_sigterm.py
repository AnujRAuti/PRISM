"""BE-037 WS-C: the SIGTERM scenarios, run in containers.

Windows host processes cannot receive SIGTERM at all (Python's `os.kill` maps it
to TerminateProcess), so the two shutdown-during-wait cases mandated by the task
can only be measured where the real signal is delivered: the worker as container
PID 1. That is also the deployment shape, so it is the more honest place to
measure it.

Cases:
  sigterm_during_retry_delay    - Redis unreachable, a long backoff wait is in
                                  progress when SIGTERM arrives.
  sigterm_during_blocked_dequeue - Redis reachable and idle, the worker is parked
                                  in BRPOPLPUSH with a 20s block.
  sigterm_short_block_contrast  - identical, block 1s, to isolate what the block
                                  value costs in shutdown latency.
  sigterm_during_long_job       - SIGTERM lands while a job is genuinely running
                                  (DB status 'running' is re-checked immediately
                                  before the stop), proving the in-flight job
                                  completes and acknowledges rather than being
                                  killed at the point of the signal.

Everything runs on this run's own network and its own containers; the protected
pofa_* resources are never referenced. The env file holds this run's throwaway
credentials and is passed with --env-file so no value is ever echoed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
sys.path.insert(0, str(REPO))
PY = str(REPO / "backend/.venv312_repro/Scripts/python.exe")
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
RUN_ID = "be037fin7c1f1"
NETWORK = f"{RUN_ID}_net"
IMAGE = "poa-backend:be037final"
REDIS_CONTAINER = f"{RUN_ID}_redis"
ENV_FILE = HERE / "worker-container.env"

DB_URL = f"postgresql+psycopg2://postgres:{RUN_ID}pw@db:5432/{RUN_ID}_app"
REDIS_URL = f"redis://redis:6379/0"
# A closed port on the reachable Redis host: the connection attempt fails at
# once, which is exactly the state a long retry wait is entered from.
REDIS_CLOSED_PORT = "redis://redis:6399/0"


def base_env(**overrides: str) -> dict[str, str]:
    env = {
        "ENVIRONMENT": "development",
        "DATABASE_URL": DB_URL,
        "REDIS_URL": REDIS_URL,
        "S3_ENDPOINT": "http://minio:9000",
        "S3_ACCESS_KEY": f"{RUN_ID}admin",
        "S3_SECRET_KEY": f"{RUN_ID}secret",
        "S3_USE_SSL": "false",
        "S3_QUARANTINE_BUCKET": f"{RUN_ID}-quarantine",
        "S3_EVIDENCE_BUCKET": f"{RUN_ID}-evidence",
        "ANALYSIS_QUEUE_NAME": f"{RUN_ID}:analysis:jobs",
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
    env.update(overrides)
    return env


def docker(*args: str, timeout: int = 300) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def inspect(container: str, field: str) -> str:
    _, out, _ = docker("inspect", "-f", field, container)
    return out


def start(name: str, env: dict[str, str]) -> None:
    lines = "\n".join(f"{k}={v}" for k, v in env.items())
    ENV_FILE.write_text(lines + "\n", encoding="utf-8")
    rc, out, err = docker(
        "run", "-d", "--name", name, "--network", NETWORK, "--restart", "no",
        "--env-file", str(ENV_FILE), IMAGE,
        "python", "-m", "backend.workers.analysis_worker",
    )
    if rc != 0:
        # Only the command shape is echoed; the env file contents stay on disk.
        raise RuntimeError(f"docker run failed rc={rc} err={err[:400]}")
    log(f"started {name}")


def container_logs(name: str) -> list[str]:
    """The worker's own lines.

    ``logging.basicConfig`` (analysis_worker.py:378) takes no stream argument, so
    it writes to stderr; reading only docker's stdout would silently drop every
    log line the evidence is supposed to quote. Both streams are container output
    here, so merge them.
    """
    _, out, err = docker("logs", name, timeout=60)
    return (out + "\n" + err).splitlines()


def wait_for_log(name: str, needle: str, timeout: float) -> tuple[float, str] | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        for line in container_logs(name):
            if needle in line:
                return round(time.monotonic() - t0, 2), line
        time.sleep(0.4)
    return None


def stop_and_measure(name: str, grace: int) -> dict:
    t0 = time.monotonic()
    rc, _, _ = docker("stop", "-t", str(grace), name, timeout=grace + 60)
    latency = round(time.monotonic() - t0, 2)
    return {
        "docker_stop_rc": rc,
        "stop_command_wall_s": latency,
        "state": inspect(name, "{{.State.Status}}"),
        "exit_code": inspect(name, "{{.State.ExitCode}}"),
        "oom_killed": inspect(name, "{{.State.OOMKilled}}"),
        "restart_count": inspect(name, "{{.RestartCount}}"),
        "stopped_at": inspect(name, "{{.State.FinishedAt}}"),
    }


def logs(name: str) -> list[str]:
    return container_logs(name)


def remove(name: str) -> None:
    docker("rm", "-f", name)


def case_retry_delay() -> dict:
    name = f"{RUN_ID}_wsig_delay"
    remove(name)
    env = base_env(
        REDIS_URL=REDIS_CLOSED_PORT,
        ANALYSIS_RETRY_BACKOFF_BASE_SECONDS="40",
        ANALYSIS_RETRY_BACKOFF_MAX_SECONDS="60",
        ANALYSIS_SHUTDOWN_POLL_SECONDS="0.5",
    )
    start(name, env)
    hit = wait_for_log(name, "redis unavailable; backing off", 90)
    stated = None
    if hit:
        import re

        match = re.search(r"backing off ([\d.]+)s", hit[1])
        stated = float(match.group(1)) if match else None
    time.sleep(2)
    remaining_upper = None if stated is None else round(stated - 2, 2)
    remaining_lower = None if stated is None else max(0.0, round(stated / 2 - 2, 2))
    result = {
        "case": "SIGTERM during a retry backoff wait",
        "configured": {
            "backoff_base_s": 40,
            "backoff_max_s": 60,
            "shutdown_poll_s": 0.5,
            "redis_url": "redis://redis:6399/0 (closed port)",
        },
        "first_backoff_warning": hit,
        "stated_delay_s": stated,
        "approx_remaining_sleep_s": [remaining_lower, remaining_upper],
        "stop": stop_and_measure(name, 120),
        "logs": logs(name),
    }
    remove(name)
    return result


def case_blocked_dequeue(block: int, label: str) -> dict:
    name = f"{RUN_ID}_wsig_block{block}"
    remove(name)
    env = base_env(
        ANALYSIS_DEQUEUE_BLOCK_SECONDS=str(block),
        ANALYSIS_REDIS_SOCKET_TIMEOUT_SECONDS="30",
        ANALYSIS_SHUTDOWN_POLL_SECONDS="0.5",
    )
    start(name, env)
    wait_for_log(name, "analysis worker started", 60)
    # Any queued work would be consumed immediately; the queue is emptied by the
    # caller, so from here the worker is parked in the blocking read.
    time.sleep(2)
    t_stop = time.monotonic()
    result = {
        "case": label,
        "configured": {
            "dequeue_block_s": block,
            "socket_timeout_s": 30,
            "shutdown_poll_s": 0.5,
        },
        "stop": stop_and_measure(name, block + 40),
        "logs": logs(name),
    }
    remove(name)
    return result


def case_long_job() -> dict:
    name = f"{RUN_ID}_wsig_job"
    remove(name)
    queue = f"{RUN_ID}:analysis:jobs"

    sys.path.insert(0, str(HERE))
    from wsc_scenarios import Harness, fixture_evidence_and_job, job_states, reset_lists

    reset_lists(queue)
    fx = fixture_evidence_and_job(size_px=6000)
    h = Harness()
    h.enqueue(queue, fx["job_id"])

    start(name, base_env())
    # Wait until the DB itself says the job is running, so the signal is proven
    # to arrive mid-processing rather than before pickup.
    t0 = time.monotonic()
    picked = None
    while time.monotonic() - t0 < 180:
        states = job_states().get(fx["job_id"], {})
        if states.get("status") == "running":
            picked = round(time.monotonic() - t0, 2)
            break
        time.sleep(1)
    mid_states = job_states().get(fx["job_id"], {})
    result = {
        "case": "SIGTERM while a job is genuinely running",
        "fixture": fx,
        "job_picked_up_after_s": picked,
        "job_state_at_stop": mid_states,
        "stop": stop_and_measure(name, 200),
        "logs": logs(name),
    }
    time.sleep(1)
    result["job_state_after_stop"] = job_states().get(fx["job_id"], {})
    result["lists_after_stop"] = h.lists(queue)
    result["final_states_log"] = [l for l in result["logs"] if "completed" in l or "stopping" in l or "stopped" in l]
    remove(name)
    reset_lists(queue)
    return result


def main() -> int:
    EVIDENCE.mkdir(exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out: dict = {}
    if REDIS_CONTAINER and which in {"blocked", "job", "all"}:
        docker("unpause", REDIS_CONTAINER)
        docker("start", REDIS_CONTAINER)
    if which in {"delay", "all"}:
        out["sigterm_during_retry_delay"] = case_retry_delay()
        (EVIDENCE / "container_sigterm_delay.json").write_text(
            json.dumps(out["sigterm_during_retry_delay"], indent=2), encoding="utf-8")
    if which in {"blocked", "all"}:
        for block, label in ((20, "SIGTERM during a blocked dequeue (20s block)"),
                             (1, "SIGTERM during a blocked dequeue (1s block, contrast)")):
            r = case_blocked_dequeue(block, label)
            key = f"sigterm_blocked_dequeue_{block}s"
            out[key] = r
            (EVIDENCE / f"container_{key}.json").write_text(
                json.dumps(r, indent=2), encoding="utf-8")
    if which in {"job", "all"}:
        r = case_long_job()
        out["sigterm_during_long_job"] = r
        (EVIDENCE / "container_sigterm_during_job.json").write_text(
            json.dumps(r, indent=2), encoding="utf-8")
    (EVIDENCE / f"container_sigterm_{which}.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    log(f"captured: {sorted(k for k in out if k != 'case')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
