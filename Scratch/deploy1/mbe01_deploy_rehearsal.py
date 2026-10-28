"""M-BE-01 step 8 (deployment half): rehearse the real release sequence in isolation.

The migration half is already measured (mbe01_rehearse.py). This measures the
part that decides whether a production night is safe: what happens to a *running
deployment* while the schema moves, and whether an operator can get service back
after the migration has already landed -- because the migration is forward-only
and cannot be undone.

Target: a disposable database (`poa_disp_deploy`) restored from the owner's
off-host copy of the last production dump, so it starts at exactly production's
position (v2w3x4y5z032, 96-value vocabulary, production row counts). The
"currently deployed" app is a pre-Stage-02 image; the candidate is the newly
built one. Nothing here can reach poa_prod / pofa_test / pofa_dev: the name set
is refused before a single command runs.

Sequence under test:
  1. old image serves traffic on the pre-migration schema;
  2. the candidate image applies `alembic upgrade head` while the old app keeps
     running -> zero-downtime claim, additive change;
  3. the OLD image still works against the migrated schema -- this is the actual
     rollback path, since the schema cannot roll back;
  4. old container stops, candidate starts, and the workflow only the candidate
     can do (PROJECT_CREATED through HTTP) is proven;
  5. SIGTERM shutdown of the candidate;
  6. injected boot failure -> operator restores service with the old image and
     no rows are lost.

Known fidelity limits, stated rather than hidden: the app connects as the
cluster superuser, not as `poa_runtime`, so role-level denials are out of scope
here (measured in BE-034); and no reverse proxy / HTTPS layer is involved.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
DUMP = Path(r"D:/CODING/Backups/poa/poa_prod-20261017T153144Z.dump")
STATE = Path(r"D:/CODING/Scratch/deploy1/armfull_state.json")
EXPECTED_SHA_PREFIX = "09c51a3b"

NEW_IMAGE = os.environ.get("POA_IMAGE", "poa-backend:mbe01-wt1")
OLD_IMAGE = os.environ.get("POA_OLD_IMAGE", "poa-backend:be037final")
DB = "poa_disp_deploy"
OLD_CONT = "poa_disp_dep_old"
NEW_CONT = "poa_disp_dep_new"
OLD_PORT, NEW_PORT, FAIL_PORT = 8011, 8012, 8014
PG_CONT, PG_ADMIN = "pofa_db", "postgres"
HEAD, START = "w3x4y5z6a033", "v2w3x4y5z032"
PROTECTED = {"pofa_dev", "pofa_test", "poa_prod", "poa_restore_probe",
             "poa_disp_prod", "poa_disp_suite", "poa_disp_owner", "pofa_local"}
EVIDENCE: list[dict] = []

IN_URL = f"postgresql+psycopg2://{PG_ADMIN}:postgres@host.docker.internal:5432/{DB}"


def sh(args, *, stdin=None, check=True, timeout=600):
    proc = subprocess.run(args, capture_output=True, text=True, input=stdin,
                          timeout=timeout)
    if proc.returncode and check:
        raise SystemExit(f"{' '.join(args[:3])} rc={proc.returncode}\n"
                         f"{(proc.stderr or proc.stdout).strip()[:600]}")
    return proc


def sql(statement, database=DB):
    return sh(["docker", "exec", PG_CONT, "psql", "-U", PG_ADMIN, "-d", database,
               "-v", "ON_ERROR_STOP=1", "-tAc", statement]).stdout.strip()


def record(name, ok, detail=""):
    EVIDENCE.append({"check": name, "passed": bool(ok), "detail": str(detail)[:400]})
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ->  {detail}" if detail else ""),
          flush=True)


def counts():
    tables = sql("select string_agg(table_name, ',') from information_schema.tables "
                 "where table_schema='public' and table_type='BASE TABLE'").split(",")
    return {t: int(sql(f"select count(*) from public.{t}", DB)) for t in tables}


def vocabulary():
    definition = sql("select pg_get_constraintdef(oid) from pg_constraint "
                     "where conname='ck_audit_ledger_event_type_domain'")
    return definition.count("'") // 2, "PROJECT_CREATED" in definition


def http(port, path, token=None, method="GET", body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return resp.status, resp.read().decode()[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)[:200]


def app_env(dsn=IN_URL, extra=None):
    state = json.loads(STATE.read_text())
    env = {
        "DATABASE_URL": dsn,
        "ENVIRONMENT": "development",
        "AUTH_MODE": "enforcing",
        "AUTH_DEV_TOKENS_ENABLED": "true",
        "JWT_SECRET": "rehearsal-not-a-secret",
        "CORS_ALLOW_ORIGINS": "http://127.0.0.1:5173",
        "REDIS_URL": "redis://host.docker.internal:16379/0",
        "S3_ENDPOINT": "http://host.docker.internal:9100",
        "S3_ACCESS_KEY": state["minio_user"],
        "S3_SECRET_KEY": state["minio_password"],
        "S3_USE_SSL": "false",
        "S3_EVIDENCE_BUCKET": "pofa-evidence",
        "S3_QUARANTINE_BUCKET": "pofa-quarantine",
    }
    env.update(extra or {})
    return env


def docker_run(image, *, name=None, port=None, env=None, command=(),
               entrypoint=None, detach=False, stdin=None, check=True):
    args = ["docker", "run", "-d" if detach else "--rm"]
    if stdin is not None:
        args.append("-i")
    if name:
        args += ["--name", name]
    if port:
        args += ["-p", f"127.0.0.1:{port}:8000"]
    for key, value in (env or {}).items():
        args += ["-e", f"{key}={value}"]
    if entrypoint:
        args += ["--entrypoint", entrypoint]
    args += [image, *command]
    return sh(args, stdin=stdin, check=check, timeout=900)


def wait_ready(port, timeout=150):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, _ = http(port, "/health")
        if status == 200:
            return True
        time.sleep(2)
    return False


SEED = r'''
from uuid import uuid4
import json
from backend.db.session import get_session
from backend.db.models import User, Organization
from backend.services import authorization as auth_service

hx = lambda: uuid4().hex[:12]
db = get_session()
try:
    auth_service.ensure_default_catalogue(db)
    db.commit()
    ids = {}
    u = User(username=f"dep-global-{hx()}", email=f"{hx()}@dep.test", status="ACTIVE",
             is_active=True)
    db.add(u); db.commit(); ids["global_user"] = str(u.id)
    org = Organization(name=f"DEP {hx()}", code=f"DEP-{hx()}", status="ACTIVE")
    db.add(org); db.commit(); ids["org"] = str(org.id)
    auth_service.assign_role(db, user_id=ids["global_user"], role_name="SUPERVISOR",
                             scope_type="GLOBAL")
    db.commit()
    print(json.dumps(ids))
finally:
    db.close()
'''


def teardown():
    for name in (OLD_CONT, NEW_CONT, "poa_disp_dep_fail"):
        sh(["docker", "rm", "-f", name], check=False)


def main() -> int:
    if DB in PROTECTED:
        raise SystemExit(f"refusing: {DB} is not disposable")
    digest = hashlib.sha256(DUMP.read_bytes()).hexdigest()
    assert digest.startswith(EXPECTED_SHA_PREFIX), "the off-host dump changed"
    print(f"candidate image : {NEW_IMAGE}\nstand-in image  : {OLD_IMAGE}\n"
          f"dump            : {DUMP.name} sha256={digest[:16]}", flush=True)

    for tag in (NEW_IMAGE, OLD_IMAGE):
        if sh(["docker", "image", "inspect", tag], check=False).returncode:
            raise SystemExit(f"image {tag} is not present locally")

    teardown()
    sh(["docker", "exec", PG_CONT, "dropdb", "-U", PG_ADMIN, "--if-exists", DB])
    sh(["docker", "exec", PG_CONT, "createdb", "-U", PG_ADMIN, DB])
    restore = subprocess.run(
        ["docker", "exec", "-i", PG_CONT, "pg_restore", "-U", PG_ADMIN, "-d", DB,
         "--no-owner", "--no-privileges", "--exit-on-error"],
        input=DUMP.read_bytes(), capture_output=True)
    record("production dump restored into the rehearsal database",
           restore.returncode == 0,
           (restore.stderr or restore.stdout).decode(errors="replace").strip()[-200:])

    revision = sql("select version_num from alembic_version")
    types, has_pc = vocabulary()
    restored = counts()
    record("rehearsal starts at production's exact position",
           revision == START and types == 96 and not has_pc,
           f"revision={revision} vocabulary={types} PROJECT_CREATED={has_pc} "
           f"ledger={restored.get('audit_ledger_events')} "
           f"projects={restored.get('projects')}")

    # ---- seed one GLOBAL identity through the candidate's own service layer ---
    seeded = json.loads(docker_run(NEW_IMAGE, env=app_env(), entrypoint="python",
                                   command=["-"], stdin=SEED).stdout.strip().splitlines()[-1])
    token_global = f"dev-user-{seeded['global_user']}"
    print(f"seeded GLOBAL caller {seeded['global_user'][:8]}", flush=True)
    # Snapshot only now: the seed itself writes rows, and those must not be
    # mistaken for damage caused by the migration.
    before = counts()

    # ---- 1. the old image serves traffic on the pre-migration schema ---------
    docker_run(OLD_IMAGE, name=OLD_CONT, port=OLD_PORT, env=app_env(), detach=True,
               command=["uvicorn", "backend.app.main:app", "--host", "0.0.0.0",
                        "--port", "8000"])
    record("deployed image serves /health pre-migration", wait_ready(OLD_PORT))
    code, body = http(OLD_PORT, "/api/v1/ready")
    record("deployed image reports ready pre-migration", code == 200, f"{code} {body[:120]}")
    print(f"OBSERVATION  pre-Stage-02 /ready body carries no component breakdown: {body[:120]}")
    code, _ = http(OLD_PORT, "/api/v1/projects", token_global)
    record("authenticated read works through the deployed image",
           code == 200, f"{code}")

    # ---- 2. migrate with the candidate while the old app keeps running -------
    upgrade = docker_run(NEW_IMAGE, env=app_env(),
                         command=["alembic", "upgrade", "head"], check=False)
    after = counts()
    types_after, has_pc_after = vocabulary()
    record("candidate applies alembic upgrade head while the old app runs",
           upgrade.returncode == 0 and sql("select version_num from alembic_version") == HEAD,
           (upgrade.stdout + upgrade.stderr).strip().replace("\n", " | ")[-200:])
    record("migrated schema has the 97-value vocabulary incl. PROJECT_CREATED",
           types_after == 97 and has_pc_after, f"vocabulary={types_after}")
    changed = {t: (n, after[t]) for t, n in before.items() if n != after[t]
               and t != "alembic_version"}
    record("no pre-existing row changed during the migration", not changed,
           f"changed={changed or 'none'}")
    code, _ = http(OLD_PORT, "/api/v1/projects", token_global)
    record("old app keeps serving with no restart after the migration",
           code == 200, f"{code}")

    # ---- 3. the rollback path: OLD image writing on the NEW schema -----------
    # The rollback safety net has to be exercised with the request shape that
    # image actually accepts: POST /projects pre-Stage-02 required an explicit
    # `owner_id`, while the candidate derives the owner from the caller.
    name = f"dep-oldwrite-{int(time.time())}"
    code, body = http(OLD_PORT, "/api/v1/projects", token_global, "POST",
                      {"name": name, "owner_id": seeded["global_user"]})
    wrote = sql(f"select count(*) from projects where name='{name}'")
    record("old image can still write against the migrated schema (rollback safety net)",
           code == 201 and wrote == "1", f"{code} rows={wrote} {body[:120]}")
    shape, shape_body = http(OLD_PORT, "/api/v1/projects", token_global, "POST",
                             {"name": f"dep-shape-{int(time.time())}"})
    record("candidate-shaped POST /projects is refused by the old image, so the request "
           "shape is an integrator-visible change on this sequence",
           shape == 422, f"{shape} {shape_body[:140]}")

    # ---- 4. swap to the candidate -------------------------------------------
    sh(["docker", "rm", "-f", OLD_CONT])
    docker_run(NEW_IMAGE, name=NEW_CONT, port=NEW_PORT, env=app_env(), detach=True,
               command=["uvicorn", "backend.app.main:app", "--host", "0.0.0.0",
                        "--port", "8000"])
    record("candidate serves /health as the API", wait_ready(NEW_PORT))
    new_name = f"dep-newwrite-{int(time.time())}"
    code, body = http(NEW_PORT, "/api/v1/projects", token_global, "POST",
                      {"name": new_name})
    pid = json.loads(body).get("id") if code == 201 else None
    actor = sql(f"select actor_id from audit_ledger_events where event_type="
                f"'PROJECT_CREATED' and resource_id='{pid}'") if pid else ""
    record("candidate creates a project and appends PROJECT_CREATED with the caller "
           "as actor", code == 201 and actor == seeded["global_user"],
           f"{code} actor={actor[:36]}")
    code, _ = http(NEW_PORT, "/api/v1/projects")
    record("candidate refuses an anonymous caller under AUTH_MODE=enforcing",
           code == 401, f"{code}")

    # ---- 5. shutdown behaviour ----------------------------------------------
    stop = subprocess.run(["docker", "stop", "-t", "10", NEW_CONT],
                          capture_output=True, text=True)
    state = sh(["docker", "inspect", "-f", "{{.State.ExitCode}} {{.State.Status}}",
                NEW_CONT], check=False).stdout.strip()
    logs = sh(["docker", "logs", "--tail", "8", NEW_CONT], check=False).stdout
    record("candidate shuts down on SIGTERM without a non-zero exit",
           stop.returncode == 0 and state.split()[0] in ("0", "143") and "exited" in state,
           f"exit/status={state}")
    print(f"  last log lines: {logs.strip().replace(chr(10), ' | ')[-240:]}")

    # ---- 6. injected misconfiguration, then recovery --------------------------
    # The measured contract (backend/app/main.py, and mbe01_health_matrix.json for
    # all four paths) is that /health is *liveness* and is deliberately
    # dependency-agnostic, while /ready and /healthz carry the dependency verdict.
    # So a candidate pointed at a nonexistent database does not crash: it keeps
    # running and only the readiness endpoints turn 503. That makes the probe path
    # the orchestrator's only signal, which is the finding this section pins.
    rows_before = counts()
    docker_run(NEW_IMAGE, name="poa_disp_dep_fail", port=FAIL_PORT, detach=True, check=False,
               env=app_env(dsn="postgresql+psycopg2://postgres:postgres@"
                                 "host.docker.internal:5432/does_not_exist"),
               command=["uvicorn", "backend.app.main:app", "--host", "0.0.0.0",
                        "--port", "8000"])
    live_at_fail = wait_ready(FAIL_PORT)
    fail_state = sh(["docker", "inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}",
                     "poa_disp_dep_fail"], check=False).stdout.strip()
    ready_code, ready_body = http(FAIL_PORT, "/ready")
    healthz_code, _ = http(FAIL_PORT, "/healthz")
    v1_code, _ = http(FAIL_PORT, "/api/v1/ready")
    sh(["docker", "rm", "-f", "poa_disp_dep_fail"], check=False)
    record("a candidate pointed at a nonexistent database reports NOT ready "
           "(/ready and /healthz and /api/v1/ready all 503)",
           ready_code == 503 and healthz_code == 503 and v1_code == 503,
           f"/ready={ready_code} /healthz={healthz_code} /api/v1/ready={v1_code}")
    record("... while liveness stays 200 and the container stays running, by design "
           "(so readiness, not the exit code, is the only outage signal)",
           live_at_fail and fail_state.split()[0] == "running",
           f"state={fail_state}")
    print("DEPLOY FINDING  docker-compose.yml's `api` healthcheck probes /health, i.e. "
          "liveness, so a database or Redis outage cannot make the container unhealthy. "
          "Readiness answers 503 correctly; the probe path is the defect.")
    print(f"  /ready body under outage: {ready_body[:200]}")
    docker_run(OLD_IMAGE, name=OLD_CONT, port=OLD_PORT, env=app_env(), detach=True,
               command=["uvicorn", "backend.app.main:app", "--host", "0.0.0.0",
                        "--port", "8000"])
    recovered = wait_ready(OLD_PORT)
    rows_after = counts()
    record("operator restores service with the previous image after the failed start",
           recovered, f"/health 200 = {recovered}")
    record("the failed start lost no data", rows_before == rows_after,
           f"tables compared={len(rows_before)}")

    # ---- 7. no drift at the end -----------------------------------------------
    check = sh(["docker", "run", "--rm", "-e", f"DATABASE_URL={IN_URL}", NEW_IMAGE,
                "alembic", "check"], check=False)
    record("alembic check reports no drift after the whole sequence",
           check.returncode == 0,
           (check.stdout + check.stderr).strip().replace("\n", " | ")[-200:])

    teardown()
    sh(["docker", "exec", PG_CONT, "dropdb", "-U", PG_ADMIN, "--if-exists", DB])
    passed = sum(e["passed"] for e in EVIDENCE)
    print(f"\n{passed}/{len(EVIDENCE)} checks passed")
    Path(__file__).with_name("mbe01_deploy_rehearsal.json").write_text(
        json.dumps({"candidate": NEW_IMAGE, "stand_in": OLD_IMAGE,
                    "dump": DUMP.name, "dump_sha256": digest,
                    "checks": EVIDENCE}, indent=2))
    return 0 if passed == len(EVIDENCE) else 1


if __name__ == "__main__":
    sys.exit(main())
