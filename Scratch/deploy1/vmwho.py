"""Report which database roles currently hold connections to the app database.

Hits a couple of API endpoints first so the application's own pool is warm, then
asks Postgres who is connected. Prints role and state only -- never a DSN.
"""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

REPO = Path.home() / "proof-of-action"


def env_value(key: str) -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"{key} missing")


def main() -> int:
    for path in ("/ready", "/api/v1/projects"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:8000{path}", timeout=10) as resp:
                print(f"GET {path} -> {resp.status}")
        except Exception as exc:  # HTTPError carries the status we care about
            code = getattr(exc, "code", None)
            print(f"GET {path} -> {code or exc}")

    sql = (
        "select usename, datname, state, application_name, count(*) "
        "from pg_stat_activity where pid <> pg_backend_pid() "
        "group by 1,2,3,4 order by 2,1"
    )
    proc = subprocess.run(
        ["docker", "exec", "pofa_db", "psql", "-U", env_value("POSTGRES_USER"),
         "-d", env_value("POSTGRES_DB"), "-c", sql],
        capture_output=True, text=True, cwd=REPO,
    )
    print(proc.stdout.strip() or proc.stderr.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
