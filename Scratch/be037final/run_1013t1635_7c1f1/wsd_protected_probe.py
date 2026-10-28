"""BE-037 WS-D: run the protected-target refusal over a REAL connection.

``test_verification_refusal_also_holds_over_a_real_connection`` is the one gate
test that skipped in the second-boot run: it is opt-in, because it needs a
database that *answers* with a protected name, and the protected cluster can
never be used to provide that. This run's second disposable cluster can: it is
this run's own server, on 127.0.0.1:15433, and a same-named database inside it
is a different physical database from the protected one. The guard refuses by
the name the server reports, which is precisely the property being proven, so
the refusal here is a real connection test rather than a stubbed one.

Steps, all against this run's own cluster:
  1. ``CREATE DATABASE pofa_dev`` on the disposable server (no app writes).
  2. Run the one node with POA_PROTECTED_NAME_PROBE_DATABASE_URL pointing at it
     while the suite's own database stays the disposable app database.
  3. Terminate connections and drop the probe database.

Only the read path is exercised against the protected-named database: the test
connects, asks ``SELECT current_database()``, and expects
``ProtectedDatabaseError``. Nothing is migrated, written or reset there.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_suite import armed_env, redact  # noqa: E402
from wsc_scenarios import PY, REPO, RUN_ID, EVIDENCE  # noqa: E402

DB2_PORT = 15433
MAINT_URL = (
    f"postgresql+psycopg2://postgres:{RUN_ID}pw2@127.0.0.1:{DB2_PORT}/postgres"
)
PROBE_NAME = "pofa_dev"
PROBE_URL = (
    f"postgresql+psycopg2://postgres:{RUN_ID}pw2@127.0.0.1:{DB2_PORT}/{PROBE_NAME}"
)
NODE = (
    "tests/integration/test_be029_database_safety_guard.py::"
    "test_verification_refusal_also_holds_over_a_real_connection"
)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {redact(message)}", flush=True)


def _parts(url: str) -> dict:
    """Connection kwargs, never a DSN string.

    psycopg2 refuses the SQLAlchemy ``postgresql+psycopg2`` scheme and echoes the
    whole string in the error; passing parts separately means no credential-bearing
    URL can ever reach a traceback or a log line.
    """
    from urllib.parse import unquote

    u = urlsplit(url)
    return {
        "host": u.hostname,
        "port": u.port,
        "user": u.username,
        "password": unquote(u.password or ""),
        "dbname": unquote(u.path.lstrip("/") or ""),
    }


def sql(parts: dict, statements: list[str]) -> list:
    """Run statements in their own transaction-less session; return one row list."""
    import psycopg2
    from psycopg2.extras import DictCursor

    conn = psycopg2.connect(**parts)
    conn.autocommit = True
    rows = []
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            for statement in statements:
                cur.execute(statement)
                # DDL statements have no result set; fetchall() on them raises.
                rows.append(cur.fetchall() if cur.description else [])
    finally:
        conn.close()
    return [
        [dict(r) if hasattr(r, "keys") else r for r in group] for group in rows
    ]


def main() -> int:
    out: dict = {"run_id": RUN_ID, "server": f"127.0.0.1:{DB2_PORT} (disposable)"}
    maint = _parts(MAINT_URL)

    # 0. The disposable server really is this run's. current_setting('port') reads
    #    the guest-side 5432 behind the published 15433, so the listener address and
    #    the container id are what prove this is NOT the protected cluster.
    out["before"] = sql(maint, [
        "SELECT current_database() AS connected_to, "
        "inet_server_addr()::text AS listener, inet_server_port() AS listener_port, "
        "current_setting('port') AS guest_port, "
        "count(*) FILTER (WHERE datname IN ('pofa_dev','pofa_test')) "
        "  AS existing_protected_named_databases, "
        "count(*) FILTER (WHERE datname LIKE '" + RUN_ID + "%') "
        "  AS this_runs_databases "
        "FROM pg_database"
    ])[0]
    probe = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", f"{RUN_ID}_db2"],
                           capture_output=True, text=True, timeout=60)
    out["server_container_id"] = probe.stdout.strip()
    log(f"server facts: {out['before']}")

    # 1. Create the name-collision database on this run's own server. Resumable:
    #    an earlier interrupted attempt of this script left one behind.
    sql(maint, [
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{PROBE_NAME}'",
        f'DROP DATABASE IF EXISTS "{PROBE_NAME}"',
        f'CREATE DATABASE "{PROBE_NAME}"',
    ])
    out["created"] = PROBE_NAME
    log(f"created {PROBE_NAME} on the disposable server")

    try:
        # 2. The opt-in live refusal test.
        env = armed_env()
        env["POA_PROTECTED_NAME_PROBE_DATABASE_URL"] = PROBE_URL
        cmd = [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", NODE]
        proc = subprocess.run(cmd, cwd=str(REPO), env=env,
                              capture_output=True, text=True, timeout=900)
        text = redact(proc.stdout + proc.stderr)
        (EVIDENCE / "wsd_protected_probe.pytest.log").write_text(text, encoding="utf-8")
        out["pytest_rc"] = proc.returncode
        out["pytest_tail"] = text.strip().splitlines()[-25:]
        log(f"pytest rc={proc.returncode}")
    finally:
        # 3. Teardown: nothing may remain that answers with a protected name.
        #    The disconnect races the terminate, so the DROP is retried.
        deadline = time.monotonic() + 30
        last: dict = {}
        while time.monotonic() < deadline:
            try:
                sql(maint, [
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{PROBE_NAME}'",
                    f'DROP DATABASE "{PROBE_NAME}"',
                ])
                last = {"dropped": True}
                break
            except Exception as exc:  # noqa: BLE001 - retry the teardown
                last = {"error": type(exc).__name__ + ": " + str(exc).splitlines()[0]}
                time.sleep(1)
        out["drop"] = last
        out["after_drop"] = sql(maint, [
            "SELECT count(*) AS remaining_protected_named_databases "
            "FROM pg_database WHERE datname IN ('pofa_dev','pofa_test')",
            "SELECT count(*) AS databases_now FROM pg_database "
            "WHERE datname LIKE '" + RUN_ID + "%'",
        ])
        log(f"after drop: {out['after_drop']}")

    url = urlsplit(PROBE_URL)
    out["probe_url_redacted"] = (
        f"postgresql+psycopg2://{url.username}:***@{url.hostname}:{url.port}/{url.path[1:]}"
    )
    (EVIDENCE / "wsd_protected_probe.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
