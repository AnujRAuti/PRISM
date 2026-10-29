"""PRISM Phase 5: a verified backup of poa_prod, restored and rehearsed somewhere else.

The release question this answers is not "can we dump a database" but "if the migration goes
wrong at 3am, is there a recovery point that actually rebuilds the service". So the sequence
is measured end to end: read the live facts, take the custom-format dump, checksum it on the
host, copy it off the host into controlled storage outside the repository, re-checksum the
copy (a transfer that changes bytes is not a backup), restore it into a *separate disposable
database on this laptop*, confirm the restore matches the live facts it came from, verify the
audit chain on the copy, then rehearse the exact migration the release would run - on the
copy, never on poa_prod.

poa_prod is only ever read: every statement sent to it is a SELECT or a pg_dump. Every write
lands in `poa_rehearse`, which is dropped at the end. The dump never enters the repository,
and no production content is reported - only counts.

    python Scratch/prism2/phase5_backup_rehearsal.py backup     # VM: facts + dump + copy off
    python Scratch/prism2/phase5_backup_rehearsal.py restore    # local: restore + verify
    python Scratch/prism2/phase5_backup_rehearsal.py upgrade    # local: rehearse the migration
    python Scratch/prism2/phase5_backup_rehearsal.py app        # local: app against the copy
    python Scratch/prism2/phase5_backup_rehearsal.py clean      # drop the rehearsal database
    python Scratch/prism2/phase5_backup_rehearsal.py report     # what has been proven so far
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
VM = "azureuser@172.198.77.149"
KEY = "D:/CODING/Projects/poa-submission-vm_key.pem"
STORE = Path("D:/CODING/Backups/poa")             # controlled storage: not the repository
STATE = REPO / "Scratch/prism2/phase5_state.json"
IMAGE = os.environ.get("POA_IMAGE", "poa-backend:prism-54e33b20")
REHEARSAL_DB = "poa_rehearse"
CONTAINER = "poa_rehearse_api"
VM_ROLE = "poa_owner"               # the role the VM's own container trusts, a name only
LOCAL_ROLE = "postgres"             # this laptop's disposable Postgres superuser
LOCAL_PASSWORD = "postgres"
TARGET = "w3x4y5z6a033"
PROTECTED = {"poa_prod", "pofa_dev", "pofa_test", "poa_owner", "poa_runtime", "postgres",
             "template0", "template1"}
MEASURED = ("users", "projects", "audit_ledger_events", "roles", "user_role_assignments",
            "permissions")
# Row content, hashed - the ledger's own fields and no timestamps, so two Postgres hosts
# cannot disagree about how a value looks. Counts alone would pass on a partial restore.
LEDGER_DIGEST = (
    "select coalesce(md5(string_agg(x::text,'|')),'(empty)') from ("
    "select sequence_number,event_type,action,resource_type,resource_id,payload,metadata,"
    "previous_hash,event_hash,hash_algorithm,ledger_version "
    "from audit_ledger_events order by sequence_number) x")
RESULTS: list[dict] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"check": name, "passed": bool(ok), "detail": str(detail)[:500]})
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ->  {detail}" if detail else ""),
          flush=True)


def note(name: str, detail: str) -> None:
    RESULTS.append({"check": name, "recorded": True, "detail": str(detail)[:500]})
    print(f"NOTE    {name}  ->  {detail}", flush=True)


def ssh(command: str, *, timeout: int = 600) -> tuple[int, str]:
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o",
         "StrictHostKeyChecking=no", "-i", KEY, VM, command],
        capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def vm_sql(stmt: str) -> str:
    """One read-only statement against poa_prod, sent over stdin to dodge shell quoting."""
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o",
         "StrictHostKeyChecking=no", "-i", KEY, VM,
         f"docker exec -i pofa_db psql -U {VM_ROLE} -d poa_prod -tA"],
        input=stmt, capture_output=True, text=True, timeout=180)
    return (proc.stdout or proc.stderr).strip()


def local(args, *, stdin=None, quiet=False) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=True, text=True, input=stdin, cwd=str(REPO))
    if proc.returncode and not quiet:
        raise SystemExit(f"{args[:3]} rc={proc.returncode} "
                         f"{(proc.stderr or proc.stdout).strip()[:400]}")
    return proc


def q(value: str) -> str:
    return shlex.quote(value)


def psql(stmt: str, database: str) -> str:
    """One statement against this laptop's disposable Postgres, inside its own container."""
    return local(["docker", "exec", "pofa_db", "psql", "-U", LOCAL_ROLE, "-d", database,
                  "-tAc", stmt]).stdout.strip()


def state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}


def save_state(update: dict) -> None:
    STATE.write_text(json.dumps({**state(), **update}, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- backup
def backup() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"poa_prod-{stamp}.dump"
    remote_path = f"/home/azureuser/{name}"
    local_path = STORE / name

    code, revision = ssh(f"docker exec pofa_db psql -U {VM_ROLE} -d poa_prod -tAc "
                         + q("select version_num from alembic_version"))
    if code != 0 or not revision:
        record("the VM is reachable and poa_prod reports a revision", False, revision[:200])
        return 2
    record("the VM is reachable and poa_prod reports a revision", True, revision)

    counts = {}
    for table in MEASURED:
        counts[table] = ssh(f"docker exec pofa_db psql -U {VM_ROLE} -d poa_prod -tAc "
                            + q(f"select count(*) from {table}"))[1]
    note("production row counts (rows are counted, never read)", json.dumps(counts))

    db_size = ssh(f"docker exec pofa_db psql -U {VM_ROLE} -d poa_prod -tAc "
                  + q("select pg_database_size(current_database())"))[1]
    tables = ssh(f"docker exec pofa_db psql -U {VM_ROLE} -d poa_prod -tAc "
                 + q("select count(*) from information_schema.tables "
                     "where table_schema='public' and table_type='BASE TABLE'"))[1]
    # pg_dump deliberately skips tables an extension owns (PostGIS's spatial_ref_sys): they are
    # recreated by the CREATE EXTENSION entry in the dump, so completeness is measured against
    # the tables pg_dump is responsible for, not against every base table that exists.
    dumpable = ssh(
        f"docker exec pofa_db psql -U {VM_ROLE} -d poa_prod -tAc "
        + q("select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='public' and c.relkind='r' and not exists "
            "(select 1 from pg_depend d where d.classid='pg_class'::regclass "
            "and d.objid=c.oid and d.deptype='e')"))[1]
    note("database size and table counts", f"bytes={db_size} base_tables={tables} "
         f"pg_dump-owned={dumpable} (extension-owned tables are recreated by CREATE EXTENSION)")
    ledger_digest = vm_sql(LEDGER_DIGEST)
    note("production audit ledger content digest (a hash of the rows, not the rows)",
         f"md5={ledger_digest}")

    stored = None
    try:
        code, out = ssh(f"docker exec pofa_db sh -c "
                        + q(f"pg_dump -U {VM_ROLE} -d poa_prod -Fc --no-owner "
                            f"-f /tmp/{name}"))
        record("pg_dump wrote a custom-format dump of poa_prod inside the database container",
               code == 0, out[:300])
        if code != 0:
            return 2

        code, toc = ssh(f"docker exec pofa_db sh -c "
                        + q(f"pg_restore -l /tmp/{name} | grep -cE "
                            "'^[0-9]+; [0-9]+ [0-9]+ TABLE public '"))
        record("pg_restore reads every table pg_dump owns out of the dump before it leaves the host",
               code == 0 and int(toc or "-1") == int(dumpable),
               f"TABLE entries={toc} pg_dump-owned={dumpable} (all base tables={tables})")

        code, out = ssh(f"docker cp pofa_db:/tmp/{q(name)} {q(remote_path)} && "
                        f"sha256sum {q(remote_path)} && stat -c%s {q(remote_path)}")
        if code != 0:
            record("the dump copied off the container to the host", False, out[:300])
            return 2
        remote_sha, remote_size = out.splitlines()[-2].split()[0], out.splitlines()[-1]

        STORE.mkdir(parents=True, exist_ok=True)
        raw = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "-i", KEY, VM,
             f"cat {q(remote_path)}"], capture_output=True, timeout=900).stdout
        local_path.write_bytes(raw)
        local_sha = hashlib.sha256(raw).hexdigest()
        stored = local_sha
        record("the dump is on the host and checksummed", True,
               f"sha256={remote_sha[:16]}... bytes={remote_size}")
        record("the copy in controlled storage is byte-identical to the host's dump",
               local_sha == remote_sha and len(raw) == int(remote_size),
               f"local sha256={local_sha[:16]}... bytes={local_path.stat().st_size} "
               f"(host said {remote_size})")
    finally:
        ssh(f"docker exec pofa_db rm -f /tmp/{q(name)}")
        left = ssh(f"docker exec pofa_db sh -c " + q(f"ls /tmp/{name} 2>/dev/null || echo gone"))[1]
        record("the transient copy inside the database container was removed",
               left.strip() == "gone", f"container says {left.strip()!r}")
        ssh(f"rm -f {q(remote_path)}")
        exists = ssh(f"test -f {q(remote_path)} && echo yes || echo no")[1]
        record("the transient copy on the host was removed after the verified transfer",
               exists == "no", f"host says {exists!r}")

    if stored is None:
        return 2
    save_state({"dump": str(local_path), "sha256": stored, "bytes": remote_size,
                "revision_before": revision, "counts": counts, "base_tables": tables,
                "dumpable_tables": dumpable, "ledger_digest_live": ledger_digest,
                "db_size_bytes": db_size,
                "stored_at": datetime.now(timezone.utc).isoformat()})
    print(f"\nbackup step complete: {local_path}")
    return 0


# --------------------------------------------------------------------------- restore
def _dsn(database: str) -> str:
    """The DSN a *container* uses to reach this laptop's Postgres."""
    return (f"postgresql+psycopg2://{LOCAL_ROLE}:{LOCAL_PASSWORD}"
            f"@host.docker.internal:5432/{database}")


def restore() -> int:
    doc = state()
    dump = Path(doc.get("dump", ""))
    if not dump.is_file():
        record("a verified dump exists in controlled storage", False, str(dump))
        return 2
    actual = hashlib.sha256(dump.read_bytes()).hexdigest()
    record("the stored dump still hashes to the value recorded when it was taken",
           actual == doc["sha256"], f"sha256={actual[:16]}... bytes={dump.stat().st_size}")

    if REHEARSAL_DB in PROTECTED:
        raise SystemExit("refusing: the rehearsal name is protected")
    psql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
         f"WHERE datname='{REHEARSAL_DB}' AND pid <> pg_backend_pid()", "postgres")
    local(["docker", "exec", "pofa_db", "dropdb", "-U", LOCAL_ROLE, "--if-exists",
           REHEARSAL_DB])
    local(["docker", "exec", "pofa_db", "createdb", "-U", LOCAL_ROLE, REHEARSAL_DB])

    local(["docker", "cp", str(dump), "pofa_db:/tmp/rehearse.dump"])
    proc = local(["docker", "exec", "pofa_db", "pg_restore", "-U", LOCAL_ROLE,
                  "-d", REHEARSAL_DB, "--no-owner", "/tmp/rehearse.dump"], quiet=True)
    local(["docker", "exec", "pofa_db", "rm", "-f", "/tmp/rehearse.dump"])
    restored = psql("select version_num from alembic_version", REHEARSAL_DB)
    record("the dump restored into the isolated rehearsal database without errors",
           proc.returncode == 0 and bool(restored),
           f"rc={proc.returncode} alembic={restored} "
           f"{(proc.stderr or '').strip()[-160:]}")
    record("the restored copy starts at exactly production's revision",
           restored == doc["revision_before"],
           f"rehearsal={restored} poa_prod={doc['revision_before']}")

    for table, expected in doc["counts"].items():
        actual_rows = psql(f"select count(*) from {table}", REHEARSAL_DB)
        record(f"restored {table} carries the same rows as production",
               actual_rows == str(expected), f"rehearsal={actual_rows} poa_prod={expected}")

    base_tables = psql("select count(*) from information_schema.tables "
                       "where table_schema='public' and table_type='BASE TABLE'",
                       REHEARSAL_DB)
    record("the restored schema has the same base-table count",
           base_tables == doc["base_tables"], f"rehearsal={base_tables} "
           f"poa_prod={doc['base_tables']}")

    live = vm_sql(LEDGER_DIGEST) or doc.get("ledger_digest_live", "")
    copy = psql(LEDGER_DIGEST, REHEARSAL_DB)
    digested = len(copy) == 32 and copy != "(empty)"
    record("the restored ledger rows carry the same content as production's, not just the "
           "same count", digested and live == copy,
           f"rehearsal md5={copy[:12]}... poa_prod md5={live[:12]}...")
    save_state({"restored_at": datetime.now(timezone.utc).isoformat(),
                "ledger_digest_live": live, "ledger_digest_copy": copy})
    return 0


def chain_check() -> None:
    """Run the application's own ledger verification against the restored copy."""
    source = """
import json
from backend.db.session import get_session
from backend.services import audit_ledger
verify = getattr(audit_ledger, "verify_chain", None) or getattr(
    audit_ledger, "verify_ledger", None)
if verify is None:
    print(json.dumps({"error": "no public chain verifier on this service"}))
else:
    report = verify(get_session())
    print(json.dumps(report if isinstance(report, dict) else repr(report), default=str))
"""
    proc = local(["docker", "run", "--rm", "-i", "-e", f"DATABASE_URL={_dsn(REHEARSAL_DB)}",
                  "-e", "ENVIRONMENT=development", IMAGE, "python", "-"],
                 stdin=source, quiet=True)
    line = [l for l in (proc.stdout or "").splitlines() if l.startswith("{")]
    detail = line[-1][:400] if line else (proc.stderr or "")[-300:]
    ok = bool(line) and '"error"' not in line[-1] and '"valid": false' not in line[-1]
    record("the audit chain on the restored copy runs through the shipped verifier", ok, detail)


def upgrade() -> int:
    doc = state()
    before = {table: psql(f"select count(*) from {table}", REHEARSAL_DB) for table in MEASURED}
    chain_check()
    pre_digest = psql(LEDGER_DIGEST, REHEARSAL_DB)

    proc = local(["docker", "run", "--rm", "-e", f"DATABASE_URL={_dsn(REHEARSAL_DB)}",
                  IMAGE, "alembic", "upgrade", "head"], quiet=True)
    after_rev = psql("select version_num from alembic_version", REHEARSAL_DB)
    record(f"the candidate image moves the copy from {doc.get('revision_before')} to {TARGET}",
           after_rev == TARGET, f"alembic={after_rev} rc={proc.returncode} "
           f"{((proc.stdout or '') + (proc.stderr or '')).strip()[-160:]}")

    after = {table: psql(f"select count(*) from {table}", REHEARSAL_DB) for table in MEASURED}
    lost = {t: (before[t], after[t]) for t in before if int(after[t]) < int(before[t])}
    record("the migration removed no rows from any measured table", not lost,
           json.dumps({"before": before, "after": after}))

    post_digest = psql(LEDGER_DIGEST, REHEARSAL_DB)
    record("the migration left every existing ledger row content-identical",
           pre_digest == post_digest,
           f"before md5={pre_digest[:12]}... after md5={post_digest[:12]}...")

    declared = local(["docker", "run", "--rm", "-i", IMAGE, "python", "-"], stdin="""
from backend.services.authorization import PERMISSIONS
print(len(PERMISSIONS))
print(",".join(sorted(PERMISSIONS)))
""", quiet=True).stdout.split()
    code_names = set(declared[1].split(",")) if len(declared) >= 2 else set()
    permission_rows = psql("select count(*) from permissions", REHEARSAL_DB)
    present = set(psql("select string_agg(name,',') from permissions", REHEARSAL_DB).split(","))
    missing = sorted(code_names - present)
    note("the migration's own effect on the catalogue",
         f"rows={permission_rows} declared_by_code={len(code_names)} not_in_db={missing} "
         "- the 032->033 revision widens the audit vocabulary only; the rows the code declares "
         "are inserted by the startup catalogue bootstrap, which the app step measures next")
    record("no permission row exists that the shipped code does not declare",
           not (present - code_names) and bool(code_names),
           f"extra={sorted(present - code_names)[:8]} declared={len(code_names)}")

    drift = local(["docker", "run", "--rm", "-e", f"DATABASE_URL={_dsn(REHEARSAL_DB)}",
                   IMAGE, "alembic", "check"], quiet=True)
    text = ((drift.stdout or "") + (drift.stderr or "")).strip()
    record("alembic reports no schema drift after the upgrade",
           drift.returncode == 0 and ("No new upgrade operations detected" in text
                                      or "No differences" in text),
           f"rc={drift.returncode} {text[-200:]}")
    save_state({"revision_after": after_rev, "counts_after": after,
                "ledger_digest_pre_migration": pre_digest,
                "ledger_digest_post_migration": post_digest,
                "permission_rows": permission_rows, "drift": text[-200:]})
    return 0 if after_rev == TARGET and not lost else 1


def app() -> int:
    """The candidate application, against the migrated copy, over real HTTP."""
    doc = state()
    local(["docker", "rm", "-f", CONTAINER], quiet=True)
    dsn = _dsn(REHEARSAL_DB)
    local(["docker", "run", "-d", "--name", CONTAINER, "-p", "127.0.0.1:8013:8000",
           "-e", f"DATABASE_URL={dsn}",
           # A loopback-only smoke of schema compatibility: development mode with dev
           # bearer tokens, so the write path can be exercised without a provider token.
           # The production posture (enforcing, OIDC on, dev tokens off) is what the
           # Phase 3 matrix and mbe01_oidc_boot measure, not this step.
           "-e", "ENVIRONMENT=development", "-e", "AUTH_MODE=development",
           "-e", "AUTH_DEV_TOKENS_ENABLED=true", "-e", "AUTH_OIDC_ENABLED=false",
           "-e", "REDIS_URL=redis://host.docker.internal:6379/0",
           "-e", "S3_ENDPOINT=http://host.docker.internal:9000",
           "-e", "S3_ACCESS_KEY=minioadmin", "-e", "S3_SECRET_KEY=minioadmin",
           IMAGE], quiet=True)
    def fetch(path, max_chars=8000):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:8013{path}", timeout=15) as response:
                return response.status, response.read().decode()[:max_chars]
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()[:max_chars]
        except (urllib.error.URLError, OSError):
            return 0, ""

    code, body = 0, ""
    deadline = time.time() + 180
    while time.time() < deadline:
        code, body = fetch("/ready")
        if code:
            break
        time.sleep(2)
    record("the candidate app answers HTTP against the migrated schema", bool(code),
           f"GET /ready http={code}")
    if not code:
        print(local(["docker", "logs", CONTAINER], quiet=True).stdout[-1200:])
        return 1

    legs = {}
    try:
        legs = {name: check.get("status")
                for name, check in json.loads(body).get("checks", {}).items()}
    except json.JSONDecodeError:
        pass
    required = {}
    try:
        required = {name: check.get("required", True)
                    for name, check in json.loads(body).get("checks", {}).items()}
    except json.JSONDecodeError:
        pass
    record("the root readiness report names every dependency leg healthy on the migrated copy",
           code == 200 and bool(legs) and all(status == "healthy" for status in legs.values())
           and all(name in legs for name, is_required in required.items() if is_required),
           f"http={code} legs={json.dumps(legs)}")

    bootstrap = local(["docker", "exec", "-i", CONTAINER, "python", "-"], stdin="""
from sqlalchemy import text
from backend.db.session import get_session
from backend.services import authorization as authz
db = get_session()
before = db.execute(text("select count(*) from permissions")).scalar_one()
authz.ensure_default_catalogue(db)
after = db.execute(text("select count(*) from permissions")).scalar_one()
print(f"{before}|{after}")
""", quiet=True).stdout.strip().splitlines()
    pair = [l for l in bootstrap if "|" in l]
    if pair:
        grew_before, grew_after = pair[-1].split("|")
        record("the shipped idempotent bootstrap closes the catalogue shortfall on the copy",
               int(grew_after) > int(grew_before),
               f"permissions rows {grew_before} -> {grew_after} after "
               "ensure_default_catalogue() (the function no production caller invokes)"
               + ("" if int(grew_after) > int(grew_before) else
                  " - a {b}->{b} reading means this copy already had the bootstrap applied; "
                  "re-run restore+upgrade for a fresh copy".format(b=grew_after)))

    catalogue = local(["docker", "exec", "-i", CONTAINER, "python", "-"], stdin="""
from sqlalchemy import text
from backend.db.session import get_session
from backend.services.authorization import PERMISSIONS
rows = {name for (name,) in get_session().execute(text("select name from permissions"))}
print(f"{len(PERMISSIONS)}|{len(rows)}|{','.join(sorted(PERMISSIONS - rows))}")
""", quiet=True).stdout.strip().splitlines()
    line = [l for l in catalogue if "|" in l]
    declared_n, present_n, missing = (line[-1].split("|") + ["?", "?", ""])[:3] if line \
        else ("?", "?", "?")
    record("the copy's catalogue now matches exactly what the shipped code declares",
           bool(line) and line[-1].count("|") == 2 and declared_n == present_n,
           f"declared={declared_n} rows={present_n} still_missing=[{missing[:120]}] "
           "- reached by calling ensure_default_catalogue() from this probe, not by the "
           "container's own startup sequence")

    owner = local(["docker", "exec", "-i", CONTAINER, "python", "-"], stdin="""
from backend.db.session import get_session
from backend.db.models import User
from backend.services import authorization as authz
db = get_session()
try:
    user = authz.create_user(db, username="prism-rehearsal-owner",
                             email="prism-rehearsal@invalid", display_name="rehearsal owner")
    db.commit()
except Exception:
    db.rollback()
    user = db.query(User).filter(User.username == "prism-rehearsal-owner").one()
authz.assign_role(db, user_id=str(user.id), role_name="SUPERVISOR", scope_type="GLOBAL",
                  actor_id=None)
db.commit()
print(user.id)
""", quiet=True).stdout.strip().splitlines()
    user_id = owner[-1] if owner else ""

    def api(method, path, token=None, payload=None, max_chars=20000):
        req = urllib.request.Request(f"http://127.0.0.1:8013/api/v1{path}", method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        data = json.dumps(payload).encode() if payload is not None else None
        try:
            with urllib.request.urlopen(req, data=data, timeout=30) as response:
                return response.status, response.read().decode()[:max_chars]
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()[:max_chars]

    principal = api("GET", "/auth/me", f"dev-user-{user_id}")
    roles, perms, parsed = [], [], False
    try:
        document = json.loads(principal[1])
        parsed = True
        roles = document.get("roles", [])
        perms = document.get("permissions", [])
    except json.JSONDecodeError:
        pass
    record("the migrated copy resolves the application's own identity endpoint",
           principal[0] == 200 and parsed and roles == ["SUPERVISOR"]
           and "project.create" in perms,
           f"http={principal[0]} roles={roles} permissions={len(perms)} "
           f"project.create={'project.create' in perms} body_chars={len(principal[1])}")

    projects_before = psql("select count(*) from projects", REHEARSAL_DB)
    refused, refused_body = api("POST", "/projects", None, {"name": "PRISM anonymous"})
    projects_after = psql("select count(*) from projects", REHEARSAL_DB)
    # Which layer refused is configuration-dependent and is recorded, not assumed:
    # under AUTH_MODE=enforcing the project.create guard answers 401/403, while under
    # development mode that guard is bypassed and the service layer refuses the write
    # because the caller has no identity to own the project.
    refused_by_guard = refused in (401, 403)
    refused_by_service = refused == 422 and "owner_id is required" in refused_body
    record("no unauthenticated write creates a project (the 201 below is not an open door)",
           not (200 <= refused < 300) and projects_before == projects_after
           and (refused_by_guard or refused_by_service),
           f"http={refused} projects={projects_before} -> {projects_after} "
           f"layer={'authorization guard' if refused_by_guard else 'service owner-derivation check'} "
           f"detail={refused_body[:110]}")

    pre_post = psql("select count(*) from audit_ledger_events", REHEARSAL_DB)
    code, body = api("POST", "/projects", f"dev-user-{user_id}", {"name": "PRISM rehearsal"})
    record("the workflow only the new schema supports (PROJECT_CREATED) runs over HTTP",
           code in (200, 201), f"http={code} body={body[:200]}")
    ledger = psql("select count(*) from audit_ledger_events", REHEARSAL_DB)
    record("the audit ledger accepted the new event",
           int(ledger) > int(pre_post), f"rows {pre_post} -> {ledger} for this request")
    chain_check()
    local(["docker", "rm", "-f", CONTAINER], quiet=True)
    return 0


def clean() -> int:
    if REHEARSAL_DB in PROTECTED:
        raise SystemExit("refusing: the rehearsal name is protected")
    local(["docker", "rm", "-f", CONTAINER], quiet=True)
    local(["docker", "exec", "pofa_db", "dropdb", "-U", LOCAL_ROLE, "--if-exists",
           REHEARSAL_DB])
    left = psql("select count(*) from pg_database where datname='poa_rehearse'", "postgres")
    print(f"{REHEARSAL_DB} removed; pg_database rows left = {left}")
    return 0


def report() -> int:
    print(json.dumps(state(), indent=2))
    return 0


COMMANDS = {"backup": backup, "restore": restore, "upgrade": upgrade, "app": app,
            "clean": clean, "report": report}

if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "report"
    if kind not in COMMANDS:
        raise SystemExit(f"unknown step {kind!r}; choose from {sorted(COMMANDS)}")
    code = COMMANDS[kind]()
    if RESULTS:
        Path(__file__).with_name(f"phase5_{kind}.json").write_text(
            json.dumps({"step": kind, "checks": RESULTS}, indent=2), encoding="utf-8")
    raise SystemExit(code)
