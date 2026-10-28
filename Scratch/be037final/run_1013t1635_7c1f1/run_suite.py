"""Arm this run's disposable dependencies, run pytest, and keep credentials out.

The disposable stack's connection strings live in ``wsc_scenarios.BASE_ENV``. The
three modules added by BE-037 FINAL (WS-C redis timeouts, WS-E1 storage isolation,
WS-E2 ledger identity matrix) refuse to run unless their ``POA_DISPOSABLE_*``
environment is armed, and they hard-fail if it names a protected resource. This
script is the only place that assembles those values, and it redacts every
credential it prints or writes, so no password or key reaches a log, a report or
Git.

Usage:
    python run_suite.py <evidence-name> <pytest target> [more targets...]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from wsc_scenarios import BASE_ENV, PY, REPO, RUN_ID, EVIDENCE  # noqa: E402

# Anything that could be a secret, collected from the values rather than written
# out here as a literal, so the redaction list cannot drift from the stack.
SECRET_VALUES = {
    urlsplit(BASE_ENV["DATABASE_URL"]).password or "",
    BASE_ENV["S3_SECRET_KEY"],
    BASE_ENV["S3_ACCESS_KEY"],
}
SECRET_VALUES |= {f"{RUN_ID}pw", f"{RUN_ID}pw2"}
SECRET_VALUES.discard("")


def redact(text: str) -> str:
    for secret in sorted(SECRET_VALUES, key=len, reverse=True):
        text = text.replace(secret, "***REDACTED***")
    return text


def armed_env() -> dict:
    env = dict(os.environ)
    env.update(BASE_ENV)
    # pytest republishes TEST_DATABASE_URL as DATABASE_URL before config import;
    # both are set so a direct ``backend.core.config`` read agrees either way.
    env["TEST_DATABASE_URL"] = BASE_ENV["DATABASE_URL"]
    env["POA_DISPOSABLE_OWNER_DATABASE_URL"] = BASE_ENV["DATABASE_URL"]
    env["POA_DISPOSABLE_REDIS_URL"] = BASE_ENV["REDIS_URL"].rsplit("/", 1)[0] + "/15"
    env["POA_DISPOSABLE_REDIS_CONTAINER"] = f"{RUN_ID}_redis"
    env["POA_DISPOSABLE_MINIO_CONTAINER"] = f"{RUN_ID}_minio"
    env["POA_DISPOSABLE_DATABASE_CONTAINER"] = f"{RUN_ID}_db"
    # The unarmed shape of a run is also evidence: a module must prove it really
    # skips when its disposable dependency is absent, not merely that it can pass
    # when armed. RUN_SUITE_WITHOUT names variables to withhold.
    for withheld in os.environ.get("RUN_SUITE_WITHOUT", "").split(","):
        key = withheld.strip()
        if key:
            env.pop(key, None)
            print(f"withholding {key}", flush=True)
    return env


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    name, targets = sys.argv[1], sys.argv[2:]
    cmd = [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets]
    print(redact(f"$ {' '.join(cmd)}"), flush=True)
    proc = subprocess.run(cmd, cwd=REPO, env=armed_env(),
                          capture_output=True, text=True, timeout=3300)
    out = redact(proc.stdout + proc.stderr)
    (EVIDENCE / f"{name}.pytest.log").write_text(out, encoding="utf-8")
    summary = [line for line in out.splitlines()
               if re.search(r"^\d+ (passed|failed)|passed|failed|error", line)][-8:]
    print(f"rc={proc.returncode}")
    print("\n".join(summary))
    print(f"wrote evidence/{name}.pytest.log")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
