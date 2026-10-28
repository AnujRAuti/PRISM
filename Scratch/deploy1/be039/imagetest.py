"""Stage 2 verification of the candidate image: run it, migrate with it, create through it.

The suite proves the code; this proves the *artifact*. Everything lands in a
disposable database (`poa_disp_img`) reachable only from localhost, and the API
runs in AUTH_MODE=enforcing -- the deployed posture -- so an anonymous caller is
refused rather than silently bypassed.

Four things only a container run can measure:
  1. the image's own Alembic set reaches head w3x4y5z6a033 from an empty schema;
  2. PROJECT_CREATED is accepted by the live CHECK through the real HTTP path;
  3. P4 holds in the image: a scope-limited caller cannot name another owner;
  4. the audit actor is the caller, not the owner named in the body.

usage: python imagetest.py preflight | run | clean
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
from uuid import uuid4

IMAGE = os.environ.get("POA_IMAGE", "poa-backend:rc-26a37aa8")
COMMIT = "26a37aa8b1d7e03762afa2055074480a013d81c2"
TREE = "d98bfac83c1525eea938f2af746265afddc2566c"
REPO = r"D:/CODING/Projects/Proof-Of-Action-Final"
DB = "poa_disp_img"
CONT = "poa_disp_img_api"
HOST_PORT = 8010
PROTECTED = {"pofa_dev", "pofa_test", "poa_prod", "poa_restore_probe"}
ADMIN = "postgres"
ADMIN_PW = "postgres"
SRC_DB = "postgres"          # maintenance DB, never a project DB
# Inside the container, host-published ports are reached through the gateway.
IN_URL = f"postgresql+psycopg2://{ADMIN}:{ADMIN_PW}@host.docker.internal:5432/{DB}"
OUT_URL = f"postgresql+psycopg2://{ADMIN}:{ADMIN_PW}@localhost:5432/{DB}"
HEAD = "w3x4y5z6a033"
EVIDENCE = []


def sh(args, *, stdin=None, quiet=False):
    p = subprocess.run(args, capture_output=True, text=True, input=stdin)
    if p.returncode and not quiet:
        raise SystemExit(f"{' '.join(args[:3])} rc={p.returncode}\n"
                         f"{(p.stderr or p.stdout).strip()[:500]}")
    return p


def psql(stmt, db=SRC_DB):
    return sh(["docker", "exec", "pofa_db", "psql", "-U", ADMIN, "-d", db,
               "-tAc", stmt]).stdout.strip()


def record(name, ok, detail=""):
    EVIDENCE.append({"check": name, "passed": bool(ok), "detail": str(detail)[:400]})
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ->  {detail}" if detail else ""))


def api(method, path, token=None, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{HOST_PORT}/api/v1{path}", method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:300]}


def image_labels():
    out = sh(["docker", "inspect", "--format",
              "{{json .Config.Labels}} {{.Id}}", IMAGE]).stdout.strip()
    labels_json, image_id = out.rsplit(" ", 1)
    return json.loads(labels_json), image_id


def preflight() -> int:
    if DB in PROTECTED:
        raise SystemExit(f"refusing: {DB} is not disposable")
    labels, image_id = image_labels()
    print(f"image id (local content digest): {image_id}")
    print(f"labels: {json.dumps(labels, sort_keys=True)}")
    record("image is tagged from the released commit",
           labels.get("poa.source.commit") == COMMIT, labels.get("poa.source.commit"))
    record("image records the source tree",
           labels.get("poa.source.tree") == TREE, labels.get("poa.source.tree"))

    # The three files that define this release must exist *inside* the artifact,
    # not merely in the working tree.
    probe = ("import hashlib,importlib,sys;"
             "from backend.db.models import AUDIT_EVENT_TYPES;"
             "from backend.security import oidc;"
             "print(len(AUDIT_EVENT_TYPES),'PROJECT_CREATED' in AUDIT_EVENT_TYPES,"
             "oidc.__file__,sys.version_info[:2])")
    out = sh(["docker", "run", "--rm", "--entrypoint", "python", IMAGE, "-c",
              probe]).stdout.strip()
    print(f"in-image probe: {out}")
    record("image carries the 97-type vocabulary incl. PROJECT_CREATED",
           out.startswith("97 True"), out)
    record("image contains backend/security/oidc.py",
           "oidc.py" in out, out)

    listing = sh(["docker", "run", "--rm", "--entrypoint", "ls", IMAGE,
                  "/app/alembic/versions"]).stdout
    record("image contains the w3x4y5z6a033 migration file",
           "w3x4y5z6a033" in listing,
           ",".join(n for n in listing.split() if "w3x4" in n))

    # The release carries uncommitted fixes, so a commit label alone cannot
    # prove the artifact is current: hash the actual working-tree bytes and
    # compare them with the bytes inside /app.
    worktree = [
        "backend/api/v1/endpoints/integration.py",
        "backend/api/v1/endpoints/evidence.py",
        "backend/services/evidence_ingestion.py",
        "backend/services/evidence_request.py",
        "backend/services/field_operations.py",
    ]
    local = {}
    for rel in worktree:
        raw = (Path(REPO) / rel).read_bytes()
        local[rel] = hashlib.sha256(raw).hexdigest()
    in_image = sh(["docker", "run", "--rm", "--entrypoint", "sha256sum", IMAGE,
                   *[f"/app/{rel}" for rel in worktree]]).stdout
    image_hashes = {line.split()[1].removeprefix("/app/"): line.split()[0]
                    for line in in_image.splitlines() if len(line.split()) == 2}
    for rel in worktree:
        record(f"image bytes match the worktree: {rel}",
               image_hashes.get(rel) == local[rel],
               f"local={local[rel][:16]} image={(image_hashes.get(rel) or 'ABSENT')[:16]}")

    print(json.dumps({"passed": sum(e['passed'] for e in EVIDENCE),
                      "total": len(EVIDENCE)}, ))
    return 0 if all(e["passed"] for e in EVIDENCE) else 1


SEED = r'''
from uuid import uuid4
from backend.db.session import get_session
from backend.db.models import User, Organization
from backend.services import authorization as auth_service
import json

def hx():
    return uuid4().hex[:12]

db = get_session()
try:
    auth_service.ensure_default_catalogue(db)
    db.commit()
    ids = {}
    for key in ("global_creator", "scoped_creator", "plain"):
        u = User(username=f"imgtest-{key}-{hx()}", email=f"{hx()}@img.test",
                 status="ACTIVE", is_active=True)
        db.add(u)
        db.commit()
        ids[key] = str(u.id)
    org = Organization(name=f"IMGTEST {hx()}", code=f"IMG-{hx()}", status="ACTIVE")
    db.add(org)
    db.commit()
    ids["org"] = str(org.id)
    auth_service.assign_role(db, user_id=ids["global_creator"], role_name="SUPERVISOR",
                             scope_type="GLOBAL")
    auth_service.assign_role(db, user_id=ids["scoped_creator"], role_name="SUPERVISOR",
                             scope_type="ORGANIZATION", organization_id=ids["org"])
    db.commit()
    print(json.dumps(ids))
finally:
    db.close()
'''


def docker_run(*extra, env=None, entrypoint=None, command=(), stdin=None,
               detach=False, name=None, port=False, quiet=False):
    args = ["docker", "run", "--rm" if not detach else "-d"]
    if stdin is not None:
        args.append("-i")
    if detach and name:
        args += ["--name", name]
    if port:
        args += ["-p", f"127.0.0.1:{HOST_PORT}:8000"]
    for key, value in (env or {}).items():
        args += ["-e", f"{key}={value}"]
    if entrypoint:
        args += ["--entrypoint", entrypoint]
    args += [IMAGE, *command]
    return sh(args, stdin=stdin, quiet=quiet)


def wait_ready(timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, body = api("GET", "/health")
            if status == 200:
                return status, body
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    raise SystemExit("api never became healthy: "
                     + sh(["docker", "logs", CONT], quiet=True).stdout[-600:])


def run() -> int:
    if DB in PROTECTED:
        raise SystemExit(f"refusing: {DB} is not disposable")
    sh(["docker", "rm", "-f", CONT], quiet=True)

    # ---- 1. a truly empty disposable database -------------------------------
    psql(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
         f"WHERE datname='{DB}' AND pid <> pg_backend_pid()")
    psql(f"DROP DATABASE IF EXISTS {DB}")
    psql(f"CREATE DATABASE {DB} OWNER {ADMIN}")
    record("disposable database created empty",
           psql(f"SELECT count(*) FROM information_schema.tables "
                f"WHERE table_schema='public'", db=DB) == "0")

    # ---- 2. migrate with the image's own Alembic, nothing from the host -----
    proc = docker_run(env={"DATABASE_URL": IN_URL},
                      command=["alembic", "upgrade", "head"])
    migration_log = (proc.stdout + proc.stderr).strip().splitlines()
    tables = psql("SELECT count(*) FROM information_schema.tables "
                  "WHERE table_schema='public' AND table_type='BASE TABLE'", db=DB)
    record("image's alembic set builds the schema from empty",
           any("Running upgrade" in line for line in migration_log) and tables == "73",
           f"tables created={tables}; last log line: {migration_log[-1] if migration_log else 'none'}")
    head = psql("SELECT version_num FROM alembic_version", db=DB)
    record(f"schema reached {HEAD}", head == HEAD, head)
    allowed = psql("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                   "WHERE conname='ck_audit_ledger_event_type_domain'", db=DB)
    record("live CHECK in the migrated DB allows PROJECT_CREATED",
           "PROJECT_CREATED" in allowed,
           f"{allowed.count(chr(39))} quoted literals in the constraint definition")

    # ---- 3. seed identities through the image's own service layer -----------
    ids = json.loads(docker_run(env={"DATABASE_URL": IN_URL}, entrypoint="python",
                               command=["-"], stdin=SEED).stdout.strip().splitlines()[-1])
    print(f"seeded: {json.dumps(ids)}")

    # ---- 4. start the API as the deployment would ----------------------------
    # ENVIRONMENT stays 'development' only because the dev bearer token is the
    # sole identity available without a real issuer; the *authorization posture*
    # under test (AUTH_MODE=enforcing, no wildcard CORS) is the production one.
    env = {
        "DATABASE_URL": IN_URL,
        "ENVIRONMENT": "development",
        "AUTH_MODE": "enforcing",
        "AUTH_DEV_TOKENS_ENABLED": "true",
        "CORS_ALLOW_ORIGINS": f"http://127.0.0.1:{HOST_PORT}",
    }
    docker_run(env=env, detach=True, name=CONT, port=True)
    status, body = wait_ready()
    record("container serves /health", status == 200, body)
    rc = sh(["docker", "exec", CONT, "python", "-c",
             "import urllib.request,json;"
             "d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ready'));"
             "print(json.dumps(d))"], quiet=True)
    print(f"/ready -> {rc.stdout.strip()[:300] or rc.stderr.strip()[:300]}")

    tok_global = f"dev-user-{ids['global_creator']}"
    tok_scoped = f"dev-user-{ids['scoped_creator']}"
    tok_plain = f"dev-user-{ids['plain']}"

    # ---- 5. enforcing really means 401 in this image ------------------------
    code, body = api("GET", "/projects")
    record("anonymous request is refused (no development bypass)",
           code == 401, f"{code} {str(body)[:120]}")

    created = []

    # owner defaults to the caller
    code, body = api("POST", "/projects", tok_plain, {"name": f"img-plain-{uuid4().hex[:6]}"})
    record("plain user cannot create a project without project.create",
           code == 403, f"{code} {str(body)[:160]}")

    name_scoped = f"img-scoped-{uuid4().hex[:6]}"
    code, body = api("POST", "/projects", tok_scoped, {"name": name_scoped})
    record("organization-scoped holder creates with owner derived from principal",
           code == 201 and body.get("owner_id") == ids["scoped_creator"],
           f"{code} owner={body.get('owner_id')} org={body.get('organization_id')}")
    if code == 201:
        created.append((name_scoped, body["id"], ids["scoped_creator"]))
        born_org = psql(f"SELECT organization_id FROM projects WHERE id='{body['id']}'",
                        db=DB)
        record("birth scope is taken from the caller's grant, not the body",
               born_org == ids["org"], f"row org={born_org} seeded org={ids['org']}")
        # The pre-fix measurement was 201-then-404: the creator could not read
        # the project it had just made, because the row was born scopeless.
        read_code, read_body = api("GET", f"/projects/{body['id']}", tok_scoped)
        record("the scoped creator can read the project it created (was 404 pre-fix)",
               read_code == 200, f"{read_code} {str(read_body)[:120]}")
        print(f"OBSERVATION  ProjectResponse carries no scope field; "
              f"POST response keys = {sorted(body)}")

    # P4: a scoped caller naming a stranger must be refused
    code, body = api("POST", "/projects", tok_scoped,
                     {"name": f"img-p4-{uuid4().hex[:6]}", "owner_id": ids["plain"]})
    record("P4: scoped caller cannot install another user as owner",
           code == 403, f"{code} {str(body)[:200]}")
    record("P4 refusal wrote no project row (non-vacuous)",
           psql(f"SELECT count(*) FROM projects WHERE name LIKE 'img-p4-%'", db=DB) == "0")

    # a GLOBAL project.create holder may delegate
    name_deleg = f"img-deleg-{uuid4().hex[:6]}"
    code, body = api("POST", "/projects", tok_global,
                     {"name": name_deleg, "owner_id": ids["plain"]})
    record("global project.create may name another active owner",
           code == 201 and body.get("owner_id") == ids["plain"],
           f"{code} owner={body.get('owner_id')}")
    if code == 201:
        created.append((name_deleg, body["id"], ids["global_creator"]))

    # ---- 6. the ledger half: one PROJECT_CREATED per success, actor = caller -
    rows = psql("SELECT count(*) FROM audit_ledger_events "
                "WHERE event_type='PROJECT_CREATED'", db=DB)
    record(f"PROJECT_CREATED rows == successful creations ({len(created)})",
           rows == str(len(created)), f"rows={rows} expected={len(created)}")

    for _, project_id, caller in created:
        actor = psql("SELECT actor_id FROM audit_ledger_events "
                     f"WHERE event_type='PROJECT_CREATED' AND resource_id='{project_id}'",
                     db=DB)
        record(f"audit actor is the caller, not the named owner ({project_id[:8]})",
               actor == caller, f"actor={actor} caller={caller}")

    owner = psql("SELECT owner_id FROM projects WHERE id="
                 f"'{created[-1][1]}'", db=DB) if created else ""
    record("the delegated project really stores the named owner",
           owner == ids["plain"], f"owner={owner}")

    print(json.dumps({"passed": sum(e["passed"] for e in EVIDENCE),
                      "total": len(EVIDENCE)}))
    return 0 if all(e["passed"] for e in EVIDENCE) else 1


def clean() -> int:
    sh(["docker", "rm", "-f", CONT], quiet=True)
    psql(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
         f"WHERE datname='{DB}' AND pid <> pg_backend_pid()")
    psql(f"DROP DATABASE IF EXISTS {DB}")
    print(f"dropped {DB}; containers named poa_disp_img_* removed")
    return 0


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "preflight"
    sys.exit({"preflight": preflight, "run": run, "clean": clean}[action]())
