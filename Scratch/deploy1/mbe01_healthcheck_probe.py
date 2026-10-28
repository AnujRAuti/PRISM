"""Prove the compose healthcheck probe command, exactly as written, in both states.

The rehearsal found that the `api` healthcheck probed `/health` (dependency-
agnostic liveness), so an outage could never make the container unhealthy. The
fix changed the probe to `/healthz`. This does not trust the reasoning: it runs
the literal command from docker-compose.yml inside the candidate image against a
live stack and against an injected database outage, and checks the exit code each
time -- because the exit code is the only thing Docker looks at.

Containers are disposable and on loopback ports; the only databases touched are
disposable ones. The shared local cluster is never stopped or restarted.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
IMAGE = "poa-backend:mbe01-wt1"
STATE = Path(r"D:/CODING/Scratch/deploy1/armfull_state.json")
PG_CONT, PG_ADMIN = "pofa_db", "postgres"
GOOD_DB, CONT = "poa_disp_owner", "poa_disp_probe_chk"
PORT = 8016
EVIDENCE: list[dict] = []


def sh(args, *, check=True, timeout=300):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise SystemExit(f"{args[:3]} rc={p.returncode}\n{(p.stderr or p.stdout)[:500]}")
    return p


def record(name, ok, detail=""):
    EVIDENCE.append({"check": name, "passed": bool(ok), "detail": str(detail)[:400]})
    print(f"{'PASS' if ok else 'FAIL'}  {name}  ->  {detail}", flush=True)


def probe_command() -> str:
    """The CMD-SHELL string exactly as it appears in docker-compose.yml."""
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    test = compose["services"]["api"]["healthcheck"]["test"]
    assert test[0] == "CMD-SHELL", f"unexpected healthcheck form: {test[0]}"
    return test[1]


def start(database: str) -> None:
    sh(["docker", "rm", "-f", CONT], check=False)
    state = json.loads(STATE.read_text())
    env = {
        "ENVIRONMENT": "development", "AUTH_MODE": "enforcing",
        "AUTH_DEV_TOKENS_ENABLED": "true", "JWT_SECRET": "probe-not-a-secret",
        "CORS_ALLOW_ORIGINS": "http://127.0.0.1:5173",
        "DATABASE_URL": f"postgresql+psycopg2://{PG_ADMIN}:postgres@host.docker.internal:"
                        f"5432/{database}",
        "REDIS_URL": "redis://host.docker.internal:16379/0",
        "S3_ENDPOINT": "http://host.docker.internal:9100",
        "S3_ACCESS_KEY": state["minio_user"], "S3_SECRET_KEY": state["minio_password"],
        "S3_USE_SSL": "false",
    }
    args = ["docker", "run", "-d", "--name", CONT, "-p", f"127.0.0.1:{PORT}:8000"]
    for k, v in env.items():
        args += ["-e", f"{k}={v}"]
    args += [IMAGE, "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    sh(args)
    deadline = time.time() + 150
    while time.time() < deadline:
        if sh(["curl", "-sS", "-m", "10", "-o", "/dev/null", "-w", "%{http_code}",
               f"http://127.0.0.1:{PORT}/health"], check=False).stdout.strip() == "200":
            return
        time.sleep(3)
    raise SystemExit("container never answered /health")


def main() -> int:
    command = probe_command()
    print(f"probe under test: {command}\n", flush=True)
    found = re.search(r"http://[^\s'\"()]+", command)
    path = found.group(0) if found else "?"
    print(f"probe target path: {path}\n", flush=True)

    start(GOOD_DB)
    healthy = sh(["docker", "exec", CONT, "sh", "-c", command], check=False)
    record("the compose probe exits 0 when every dependency is up",
           healthy.returncode == 0,
           f"rc={healthy.returncode} {healthy.stderr.strip()[-120:]}")

    start("does_not_exist")
    broken = sh(["docker", "exec", CONT, "sh", "-c", command], check=False)
    record("the same probe exits non-zero when the database is gone "
           "(so Docker can see the outage at all)",
           broken.returncode != 0,
           f"rc={broken.returncode} {broken.stderr.strip().splitlines()[-1][:140]}")

    sh(["docker", "rm", "-f", CONT], check=False)
    passed = sum(e["passed"] for e in EVIDENCE)
    print(f"\n{passed}/{len(EVIDENCE)} checks passed")
    Path(__file__).with_name("mbe01_healthcheck_probe.json").write_text(
        json.dumps({"image": IMAGE, "probe": command, "target": path,
                    "checks": EVIDENCE}, indent=2))
    return 0 if passed == len(EVIDENCE) else 1


if __name__ == "__main__":
    sys.exit(main())
