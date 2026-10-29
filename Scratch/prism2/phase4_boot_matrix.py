"""PRISM Phase 4: the candidate image, on a database built from nothing, boots every
process it ships and stops cleanly when asked.

Nothing here touches an existing database: ``poa_boot4`` is created empty, migrated with
the image's own Alembic revision, used for the smoke, and dropped at the end. The API runs
in the production-shaped configuration (enforcing, provider off, development tokens off),
so the health surface is measured while the door is shut.

    python Scratch/prism2/phase4_boot_matrix.py [image]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
IMAGE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "POA_IMAGE", "poa-backend:prism-481fdc39")
DB = "poa_boot4"
API_CONT = "poa_boot4_api"
PORT = 8014
HEAD = "w3x4y5z6a033"
WORKERS: dict[str, list[str]] = {}
RESULTS: list[dict] = []
NOTES: list[dict] = []
STATE = json.loads((REPO / "Scratch/deploy1/armfull_state.json").read_text(encoding="utf-8"))


def compose_service(name: str) -> dict:
    import yaml

    document = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    return document["services"][name]


# The commands exercised below are the ones the release actually ships, read out of
# docker-compose.yml rather than copied here.
WORKERS = {name: [str(part) for part in compose_service(f"{name}_worker")["command"]]
           for name in ("analysis", "notification", "retention", "webhook")}


def sh(args, *, check=True, timeout=180):
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode:
        raise SystemExit(f"{' '.join(args[:4])} rc={proc.returncode}\n"
                         f"{(proc.stderr or proc.stdout)[:600]}")
    return proc


def record(name, ok, detail=""):
    RESULTS.append({"check": name, "pass": bool(ok), "detail": str(detail)[:500]})
    print(f"{'PASS' if ok else 'FAIL':<5} {name}" + (f"  ->  {detail}" if detail else ""),
          flush=True)


def note(name, detail=""):
    NOTES.append({"note": name, "detail": str(detail)[:500]})
    print(f"NOTE  {name}" + (f"  ->  {detail}" if detail else ""), flush=True)


def psql(stmt, database="postgres"):
    return sh(["docker", "exec", "pofa_db", "psql", "-U", "postgres", "-d", database,
               "-tAc", stmt]).stdout.strip()


def app_env():
    return {
        "ENVIRONMENT": "development",
        "AUTH_MODE": "enforcing",
        "AUTH_DEV_TOKENS_ENABLED": "false",
        "AUTH_OIDC_ENABLED": "false",
        "JWT_SECRET": "boot-matrix-not-a-secret",
        "CORS_ALLOW_ORIGINS": f"http://127.0.0.1:{PORT}",
        "DATABASE_URL": ("postgresql+psycopg2://postgres:postgres@host.docker.internal:"
                         f"5432/{DB}"),
        "REDIS_URL": "redis://host.docker.internal:16379/0",
        "S3_ENDPOINT": "http://host.docker.internal:9100",
        "S3_ACCESS_KEY": STATE["minio_user"],
        "S3_SECRET_KEY": STATE["minio_password"],
        "S3_USE_SSL": "false",
    }


def api(path, timeout=10):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1{path}",
                                    timeout=timeout) as response:
            return response.status, response.read().decode()[:800]
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()[:800]
    except (urllib.error.URLError, OSError):
        return None, ""


def root(path, timeout=10):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}",
                                    timeout=timeout) as response:
            return response.status, response.read().decode()[:800]
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()[:800]
    except (urllib.error.URLError, OSError):
        return None, ""


def wait_http(path, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        code, body = root(path)
        if code == 200:
            return code, body
        time.sleep(2)
    return None, ""


def start_container(name, command, *, ports=None):
    sh(["docker", "rm", "-f", name], check=False)
    args = ["docker", "run", "-d", "--name", name]
    if ports:
        args += ["-p", f"127.0.0.1:{PORT}:8000"]
    for key, value in app_env().items():
        args += ["-e", f"{key}={value}"]
    args += [IMAGE] + command
    sh(args)


def stop_and_measure(name, timeout=40):
    """SIGTERM, then the exit code the container actually recorded."""
    sh(["docker", "stop", "-t", "15", name], check=False, timeout=timeout + 20)
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = sh(["docker", "inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}",
                    name], check=False).stdout.strip()
        if state.split()[0] == "exited":
            status, code = state.split()
            return int(code)
        time.sleep(1)
    return None


def main() -> int:
    digest = sh(["docker", "image", "inspect", "-f",
                 "{{index .RepoDigests 0}}|{{.Id}}", IMAGE]).stdout.strip()
    record("the named image exists and resolves to a digest", bool(digest), digest[:80])
    pinned = compose_service("api").get("image")
    note("docker-compose.yml pins a different image tag; a deployment must retag or "
         "override it", f"compose api image={pinned} tested image={IMAGE}")

    # --- a database that did not exist a minute ago ------------------------------------
    sh(["docker", "exec", "pofa_db", "dropdb", "-U", "postgres", "--if-exists", DB])
    sh(["docker", "exec", "pofa_db", "createdb", "-U", "postgres", DB])
    record("an empty database was created for this smoke", True, DB)
    before = int(psql("select count(*) from pg_class where relkind='r' "
                      "and relnamespace = 'public'::regnamespace", DB))
    record("the new database has no application tables before migration", before == 0,
           f"base tables={before}")

    migrate = sh(["docker", "run", "--rm", "--entrypoint", "alembic",
                  "-e", ("DATABASE_URL=postgresql+psycopg2://postgres:postgres@"
                         f"host.docker.internal:5432/{DB}")] +
                 sum((["-e", f"{k}={v}"] for k, v in app_env().items()
                      if k != "DATABASE_URL"), []) +
                 [IMAGE, "upgrade", "head"], check=False, timeout=600)
    record("the image's own Alembic revision builds the schema from nothing",
           migrate.returncode == 0 and "error" not in migrate.stderr.lower(),
           f"rc={migrate.returncode} {migrate.stdout.strip().splitlines()[-1][:80] if migrate.stdout.strip() else migrate.stderr.strip()[:80]}")
    revision = psql("select version_num from alembic_version", DB)
    record("the built schema sits at the release revision", revision == HEAD,
           f"alembic_version={revision}")
    tables = int(psql("select count(*) from pg_class where relkind='r' "
                      "and relnamespace = 'public'::regnamespace", DB))
    record("the built schema has the expected table count", tables == 73,
           f"base tables={tables}")

    # --- the API -----------------------------------------------------------------------
    start_container(API_CONT, ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0",
                               "--port", "8000"], ports=True)
    code, body = wait_http("/health")
    record("the API answers liveness on the fresh schema", code == 200, body)
    code, body = root("/ready")
    legs = {}
    try:
        document = json.loads(body)
        sections = document.get("checks", document)
        legs = {name: str(value.get("status")) for name, value in sections.items()
                if isinstance(value, dict)}
    except (json.JSONDecodeError, AttributeError):
        pass
    record("/ready reports every dependency leg healthy", code == 200
           and legs and all(v == "healthy" for v in legs.values()), f"http={code} {legs}")
    for path in ("/healthz", "/api/v1/ready"):
        code, body = root(path)
        record(f"{path} answers", code == 200, f"http={code} {body[:60]}")

    # --- the door is shut in this configuration ---------------------------------------
    for path in ("/auth/me", "/projects"):
        code, _body = api(path)
        record(f"anonymous {path} is refused on this configuration", code == 401,
               f"http={code}")
    code, body = root("/metrics")
    record("anonymous /metrics is refused on this configuration", code == 401,
           f"http={code} {body[:60]}")

    api_exit = stop_and_measure(API_CONT)
    logs = sh(["docker", "logs", API_CONT], check=False).stdout
    record("the API shuts down gracefully on SIGTERM", api_exit == 0,
           f"exit={api_exit} shutdown_logged={'shutdown' in logs.lower()}")

    # --- the four workers --------------------------------------------------------------
    for name, command in WORKERS.items():
        cont = f"poa_boot4_{name}"
        start_container(cont, command)
        time.sleep(12)
        running = sh(["docker", "inspect", "-f", "{{.State.Running}}", cont],
                     check=False).stdout.strip()
        logs = sh(["docker", "logs", cont], check=False).stdout + \
            sh(["docker", "logs", cont], check=False).stderr
        record(f"the {name} worker starts and stays up",
               running == "true" and "Traceback" not in logs,
               f"running={running} traceback={'Traceback' in logs} "
               f"lines={len(logs.strip().splitlines())}")
        exit_code = stop_and_measure(cont)
        record(f"the {name} worker exits cleanly on SIGTERM", exit_code == 0,
               f"exit={exit_code}")
        sh(["docker", "rm", "-f", cont], check=False)

    # --- cleanup -----------------------------------------------------------------------
    sh(["docker", "rm", "-f", API_CONT], check=False)
    sh(["docker", "exec", "pofa_db", "dropdb", "-U", "postgres", "--if-exists", DB])
    left = psql(f"select count(*) from pg_database where datname='{DB}'")
    record("the disposable database was dropped, leaving no state behind", left == "0",
           f"pg_database rows={left}")

    failed = [r for r in RESULTS if not r["pass"]]
    out = REPO / "Scratch/prism2/phase4_boot_matrix.json"
    out.write_text(json.dumps({"image": IMAGE, "digest": digest, "checks": RESULTS,
                               "notes": NOTES}, indent=2), encoding="utf-8")
    print(json.dumps({"passed": len(RESULTS) - len(failed), "total": len(RESULTS)}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
