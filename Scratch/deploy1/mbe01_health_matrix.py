"""What do the four operational endpoints actually report when a dependency dies?

Measured because the compose `api` healthcheck is the thing that decides whether
an outage is visible at all, and it currently probes `/health`, which the app
documents as "liveness, dependency-agnostic". This names the real contract of
/health, /ready, /healthz and /api/v1/ready against a live stack and against two
outages, and records the response time -- a healthcheck whose probe is slower
than its own timeout flaps, which is a second finding.

Containers get their own disposable names and ports; the only databases touched
are disposable ones.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

IMAGE = "poa-backend:mbe01-wt1"
CONT = "poa_disp_health"
PORT = 8013
STATE = json.loads(Path("armfull_state.json").read_text())
TMP = Path(__file__).with_name("mbe01_health_probe_body.json")
PATHS = ("/health", "/ready", "/healthz", "/api/v1/ready")


def sh(args, check=True):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode and check:
        raise SystemExit(f"{args[:3]} rc={p.returncode}\n{(p.stderr or p.stdout)[:400]}")
    return p


def env_for(db=True, redis=True, minio=True):
    e = {
        "ENVIRONMENT": "development",
        "AUTH_MODE": "enforcing",
        "AUTH_DEV_TOKENS_ENABLED": "true",
        "JWT_SECRET": "rehearsal-not-a-secret",
        "CORS_ALLOW_ORIGINS": "http://127.0.0.1:5173",
        "DATABASE_URL": ("postgresql+psycopg2://postgres:postgres@host.docker.internal:"
                         f"5432/{'poa_disp_owner' if db else 'no_such_db'}"),
        "REDIS_URL": f"redis://host.docker.internal:16379/0" if redis else "redis://127.0.0.1:1/0",
        "S3_ENDPOINT": "http://host.docker.internal:9100" if minio else "http://127.0.0.1:1",
        "S3_ACCESS_KEY": STATE["minio_user"],
        "S3_SECRET_KEY": STATE["minio_password"],
        "S3_USE_SSL": "false",
    }
    return e


def start(env):
    sh(["docker", "rm", "-f", CONT], check=False)
    args = ["docker", "run", "-d", "--name", CONT, "-p", f"127.0.0.1:{PORT}:8000"]
    for k, v in env.items():
        args += ["-e", f"{k}={v}"]
    args += [IMAGE, "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    sh(args)
    time.sleep(20)


def probe():
    rows = []
    for path in PATHS:
        out = sh(["curl", "-sS", "-m", "40", "-o", str(TMP), "-w", "%{http_code} %{time_total}",
                  f"http://127.0.0.1:{PORT}{path}"], check=False)
        code, _, elapsed = out.stdout.partition(" ")
        body = TMP.read_text(errors="replace") if out.returncode == 0 else ""
        components = ""
        try:
            data = json.loads(body)
            checks = data.get("checks") or {}
            components = " ".join(
                f"{name}={value.get('status')}" for name, value in checks.items()
                if isinstance(value, dict)) or data.get("status", "")
        except json.JSONDecodeError:
            components = body[:60]
        rows.append((path, code, elapsed, components))
        print(f"  {path:<15} {code} {elapsed:>6}s  {components}", flush=True)
    return rows


def main() -> int:
    cases = [
        ("all dependencies live", env_for()),
        ("database unreachable", env_for(db=False)),
        ("redis unreachable", env_for(redis=False)),
    ]
    results = {}
    for label, env in cases:
        print(f"\n=== {label} ===", flush=True)
        start(env)
        results[label] = probe()
    sh(["docker", "rm", "-f", CONT], check=False)
    Path("mbe01_health_matrix.json").write_text(json.dumps(results, indent=2))
    print("\nwrote mbe01_health_matrix.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
