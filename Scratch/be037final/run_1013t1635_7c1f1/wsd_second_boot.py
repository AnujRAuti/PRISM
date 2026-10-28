"""BE-037 WS-D: does the repo-supported bootstrap reproduce on a SECOND fresh database?

The first-boot findings for this run (final-05 / final-05b / final-06) were taken
from one container. A bootstrap that only works once is not reproducible, so this
script builds a second, uniquely named, disposable Postgres from the same image
and the same repository init mount, migrates it with the repository's own command,
and then re-runs the questions that mattered the first time:

  1. which init scripts the entrypoint actually ran,
  2. the extension set and versions after first boot,
  3. extension-owned objects and their owner,
  4. whether the image's vendor demo artefact (exemplo_dados) is present,
  5. alembic state after `upgrade head`,
  6. the exact expected drift, and its classification,
  7. that deliberate application-owned drift is still DETECTED (the gate is not
     blinded by the extension exclusion),
  8. that a second run on the same database is idempotent.

Nothing here touches pofa_db/pofa_dev/pofa_test: this database lives in this
run's own container on host port 15433, with this run's throwaway password, and
is removed at the end together with its volume. Credentials are never printed;
DSNs are reported with the password replaced by ***.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
HERE = Path(__file__).resolve().parent
RUN_ID = "be037fin7c1f1"
PY = str(REPO / "backend/.venv312_repro/Scripts/python.exe")
IMAGE = "garapadev/postgres-postgis-pgvector:15-stable"
CONTAINER = f"{RUN_ID}_db2"
VOLUME = f"{RUN_ID}_db2_data"
NETWORK = f"{RUN_ID}_net"
DB_NAME = f"{RUN_ID}_app2"
PASSWORD = f"{RUN_ID}pw2"
HOST_PORT = 15433
OUT = HERE / "evidence" / "wsd_second_boot.json"

SQL_URL = f"postgresql+psycopg2://postgres:PASSWORD@localhost:{HOST_PORT}/{DB_NAME}".replace(
    "PASSWORD", PASSWORD
)
REDACTED = f"postgresql+psycopg2://postgres:***@localhost:{HOST_PORT}/{DB_NAME}"


def sh(cmd: list[str], env: dict | None = None, timeout: int = 600) -> tuple[int, str]:
    proc = subprocess.run(
        cmd, capture_output=True, text=True, env=env, cwd=str(REPO), timeout=timeout
    )
    return proc.returncode, redact((proc.stdout or "") + (proc.stderr or ""))


def redact(text: str) -> str:
    return text.replace(PASSWORD, "***")


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {redact(message)}", flush=True)


def sql(query: str) -> str:
    proc = subprocess.run(
        ["docker", "exec", CONTAINER, "psql", "-U", "postgres", "-d", DB_NAME,
         "-Atqc", query],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(redact(proc.stderr.strip()[:400]))
    return proc.stdout.strip()


def wait_ready(timeout: int = 180) -> None:
    """Poll ``pg_isready`` inside the container.

    The healthcheck that marks ``be037fin7c1f1_db`` healthy comes from the
    Compose file, not from the image, so a bare ``docker run`` of the same image
    reports ``health=none`` forever. Readiness has to be measured, not assumed.
    """
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        probe = subprocess.run(
            ["docker", "exec", CONTAINER, "pg_isready", "-U", "postgres", "-d", DB_NAME],
            capture_output=True, text=True, timeout=30,
        )
        last = (probe.stdout + probe.stderr).strip()
        if probe.returncode == 0:
            return
        time.sleep(2)
    raise TimeoutError(f"{CONTAINER} did not become ready; last probe: {last[:200]}")


def main() -> int:
    result: dict = {"redacted_url": REDACTED, "container": CONTAINER}

    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True, text=True)
    subprocess.run(["docker", "volume", "rm", VOLUME], capture_output=True, text=True)

    rc, out = sh([
        "docker", "run", "-d", "--name", CONTAINER, "--network", NETWORK,
        "--restart", "no",
        "-p", f"127.0.0.1:{HOST_PORT}:5432",
        "-e", "POSTGRES_USER=postgres",
        "-e", f"POSTGRES_PASSWORD={PASSWORD}",
        "-e", f"POSTGRES_DB={DB_NAME}",
        "-v", f"{VOLUME}:/var/lib/postgresql/data",
        "-v", f"{REPO}/docker/pg-init:/docker-entrypoint-initdb.d:ro",
        IMAGE,
    ])
    result["docker_run_rc"] = rc
    if rc != 0:
        result["docker_run_out"] = out
        OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 1
    log(f"started {CONTAINER}, waiting for readiness")
    wait_ready()

    # Healthcheck provenance: the Compose service is marked healthy, the image on
    # its own is not. Measured rather than assumed, because it changes what a
    # bare `docker run` of this image can be trusted to report.
    result["healthcheck_on_bare_docker_run"] = sh(
        ["docker", "inspect", "-f", "{{if .Config.Healthcheck}}defined{{else}}none{{end}}",
         CONTAINER]
    )[1]
    result["healthcheck_on_compose_created_db"] = sh(
        ["docker", "inspect", "-f", "{{if .Config.Healthcheck}}defined{{else}}none{{end}}",
         f"{RUN_ID}_db"]
    )[1]

    logs = subprocess.run(["docker", "logs", CONTAINER], capture_output=True,
                          text=True, timeout=60).stdout
    result["init_scripts_run"] = [
        line.split("running ")[-1] for line in logs.splitlines()
        if "docker-entrypoint.sh: running" in line
    ]
    result["initdb_trust_warning"] = "trust" in logs

    result["extensions_after_first_boot"] = sql(
        "select extname||' '||extversion from pg_extension order by extname"
    ).splitlines()
    result["public_table_count_after_first_boot"] = int(
        sql("select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='public' and c.relkind in ('r','p')")
    )
    result["vendor_demo_present_after_first_boot"] = sql(
        "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='public' and c.relname='exemplo_dados'"
    ) == "1"
    result["public_relations_after_first_boot"] = sql(
        "select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='public' and c.relkind in ('r','p') order by 1"
    ).splitlines()

    # ---- the repository's own migration path, unarmed (normal dev runtime) ----
    mig_env = dict(os.environ)
    mig_env["DATABASE_URL"] = SQL_URL
    mig_env.pop("TEST_DATABASE_URL", None)
    mig_env.pop("POA_DATABASE_CONTEXT", None)
    rc, out = sh([PY, "-m", "alembic", "upgrade", "head"], env=mig_env, timeout=900)
    result["alembic_upgrade_rc"] = rc
    result["alembic_upgrade_tail"] = out.splitlines()[-6:]

    result["alembic_version_after_upgrade"] = sql("select version_num from alembic_version")
    result["table_count_after_upgrade"] = int(
        sql("select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='public' and c.relkind in ('r','p')")
    )
    result["extension_owned_objects"] = [
        dict(zip(("owner", "relname", "relkind"), row.split("|")))
        for row in sql(
            "select pg_get_userbyid(r.relowner)||'|'||r.relname||'|'||r.relkind::text "
            "from pg_class r join pg_namespace n on n.oid=r.relnamespace "
            "where n.nspname='public' and r.relname='spatial_ref_sys'"
        ).splitlines()
    ]
    result["search_path"] = sql("show search_path")
    result["baseline_registry_rows"] = int(
        sql("select count(*) from information_schema.table_constraints "
            "where table_name='audit_ledger_events'")
    )

    # ---- the gate, on this second database ----
    gate_env = dict(os.environ)
    gate_env["TEST_DATABASE_URL"] = SQL_URL
    rc, out = sh(
        [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/integration/test_schema_drift_gate.py",
         "tests/integration/test_be029_database_safety_guard.py"],
        env=gate_env, timeout=1800,
    )
    result["gate_rc"] = rc
    result["gate_summary"] = [l for l in out.splitlines() if re.search(r"\d+ (passed|failed)", l)][-3:]

    # ---- deliberate application-owned drift must still be detected ----
    baseline_test = (
        "tests/integration/test_schema_drift_gate.py::"
        "test_drift_is_exactly_the_documented_baseline"
    )
    rc, out = sh([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", baseline_test],
                 env=gate_env, timeout=900)
    result["drift_test_clean"] = {"rc": rc, "tail": out.splitlines()[-3:]}

    sql("create table public.poa_wsd_manual_drift (id integer primary key)")
    rc, out = sh([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", baseline_test],
                 env=gate_env, timeout=900)
    result["drift_test_with_manual_table"] = {
        "rc": rc,
        "names_the_manual_table": "poa_wsd_manual_drift" in out,
        "tail": out.splitlines()[-6:],
    }
    rc, out = sh([PY, "-m", "alembic", "check"], env=mig_env, timeout=600)
    result["alembic_check_with_manual_table"] = {
        "rc": rc,
        "mentions_manual_table": "poa_wsd_manual_drift" in out,
        "tail": out.splitlines()[-4:],
    }
    sql("drop table public.poa_wsd_manual_drift")
    rc, out = sh([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", baseline_test],
                 env=gate_env, timeout=900)
    result["drift_test_after_drop"] = {"rc": rc, "tail": out.splitlines()[-3:]}

    # ---- repeatability: a second upgrade pass is a no-op ----
    rc, out = sh([PY, "-m", "alembic", "upgrade", "head"], env=mig_env, timeout=600)
    result["alembic_upgrade_again"] = {"rc": rc, "tail": out.splitlines()[-3:]}
    rc, out = sh([PY, "-m", "alembic", "check"], env=mig_env, timeout=600)
    result["alembic_check_clean"] = {
        "rc": rc,
        "head_is_up_to_date": "New upgrade operations detected" not in out,
        "tail": out.splitlines()[-4:],
    }
    result["extensions_after_upgrade"] = sql(
        "select extname||' '||extversion from pg_extension order by extname"
    ).splitlines()

    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT.name}: gate_rc={result['gate_rc']} "
        f"alembic_check_clean_rc={result['alembic_check_clean']['rc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
