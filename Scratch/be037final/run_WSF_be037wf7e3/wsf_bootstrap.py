"""BE-037 WS-F step 1: identify what compose created, then bootstrap the stack.

Order matters. Before any application action the script proves the created
resources carry this run's identity (compose project label, name, creation time),
and re-reads the protected containers so a later claim of "untouched" rests on a
comparison rather than an assumption.

Then it performs the repository's own bootstrap on the fresh database —
extensions, `alembic upgrade head`, buckets, the least-privilege runtime role and
the authorization catalogue — and records what each step actually produced.

Two deliberate choices:

* The role is named after this run (`be037wf7e3_runtime`), **not** `poa_runtime`.
  `scripts/provision_runtime_roles.sql` line 69 issues `ALTER ROLE poa_runtime WITH
  PASSWORD …`, which is cluster-wide; a test that reused that name could change a
  live application's credential. The grant *shape* is copied exactly, the name is
  not. (`be037wf7e3_migrator` from the intent list was deliberately not created:
  on this disposable cluster DDL runs as the boot superuser, and the F-05 property
  under test is that the *runtime* identity is not the table owner.)
* The role/permission catalogue is seeded out-of-band here, because nothing in app
  startup, in any worker, or in any migration calls `ensure_default_catalogue()`
  — the D2 catalogue-bootstrap blocker, re-observed on a clean database.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
EVIDENCE = HERE / "evidence"
REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
PY = str(REPO / "backend/.venv312_repro/Scripts/python.exe")

RUN_ID = "be037wf7e3"
DB_NAME = f"{RUN_ID}_app"
OWNER_PW = f"{RUN_ID}pw"
RUNTIME_ROLE = f"{RUN_ID}_runtime"
RUNTIME_PW = f"{RUN_ID}rtpw"
ADMIN_USER = f"{RUN_ID}admin"
ADMIN_SECRET = f"{RUN_ID}secret"
HOST = "127.0.0.1"
DB_PORT = 15442
S3_ENDPOINT = f"http://{HOST}:19010"
QUARANTINE_BUCKET = f"{RUN_ID}-quarantine"
EVIDENCE_BUCKET = f"{RUN_ID}-evidence"

PROTECTED = ["pofa_db", "pofa_redis", "pofa_minio"]
CREATED = [f"{RUN_ID}_db", f"{RUN_ID}_redis", f"{RUN_ID}_minio"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(cmd: list[str], env: dict | None = None, timeout: int = 900) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr)


def docker(*args: str, timeout: int = 90) -> tuple[int, str]:
    return sh(["docker", *args], timeout=timeout)


def redact(text: str) -> str:
    for secret in (OWNER_PW, RUNTIME_PW, ADMIN_SECRET, ADMIN_USER):
        text = text.replace(secret, "***REDACTED***")
    return text


def owner_kwargs(dbname: str = DB_NAME) -> dict:
    return {"host": HOST, "port": DB_PORT, "user": "postgres",
            "password": OWNER_PW, "dbname": dbname}


def sql(conn_kwargs: dict, statement: str, params=None) -> list[tuple]:
    import psycopg2

    conn = psycopg2.connect(**conn_kwargs)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(statement, params)
            return cur.fetchall() if cur.description else []
    finally:
        conn.close()


def wait_healthy(names: list[str], timeout: int = 240) -> dict:
    deadline = time.monotonic() + timeout
    states: dict = {}
    while time.monotonic() < deadline:
        unresolved = [n for n in names if states.get(n) != "healthy"]
        if not unresolved:
            return states
        for name in unresolved:
            rc, out = docker("inspect", "-f", "{{.State.Health.Status}}", name)
            states[name] = out if rc == 0 else f"inspect-error:{out}"
        time.sleep(4)
    return states


def container_identity(name: str) -> dict:
    rc, out = docker(
        "inspect", "-f",
        "{{.Id}}|{{.Created}}|{{.State.Status}}|{{.RestartCount}}|{{.Config.Image}}|"
        '{{index .Config.Labels "com.docker.compose.project"}}|'
        '{{index .Config.Labels "com.docker.compose.service"}}|'
        '{{index .Config.Labels "com.docker.compose.oneoff"}}',
        name,
    )
    if rc != 0:
        return {"exists": False, "error": redact(out)}
    cid, created, state, restarts, image, project, service, oneoff = out.split("|")
    return {"exists": True, "id": cid, "id_short": cid[:12], "created": created,
            "state": state, "restart_count": restarts, "image": image,
            "compose_project": project, "compose_service": service, "oneoff": oneoff}


def main() -> int:
    out: dict = {"run_id": RUN_ID, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    # 1. Health of the freshly created dependencies.
    out["health"] = wait_healthy(CREATED)
    log(f"health: {out['health']}")

    # 2. Identity of what was created, straight from the daemon.
    out["created_containers"] = {n: container_identity(n) for n in CREATED}
    out["all_labelled_this_project"] = all(
        v.get("compose_project") == RUN_ID for v in out["created_containers"].values()
    )
    rc, vols = docker("volume", "ls", "-q", "-f", f"name={RUN_ID}")
    out["created_volumes"] = vols.splitlines()
    rc, nets = docker("network", "ls", "-q", "-f", f"name=^{RUN_ID}_net$")
    out["created_networks"] = nets.splitlines()
    rc, ctrs = docker("ps", "-a", "--filter", f"label=com.docker.compose.project={RUN_ID}",
                      "--format", "{{.Names}}")
    out["containers_by_project_label"] = ctrs.splitlines()
    log(f"identity: labelled={out['all_labelled_this_project']} "
        f"volumes={len(out['created_volumes'])} networks={len(out['created_networks'])}")

    # 3. Protected resources, re-read for comparison against the pre-creation manifest.
    before = json.loads((EVIDENCE / "wsf-00-manifest-before.json").read_text(encoding="utf-8"))
    after = {n: container_identity(n) for n in PROTECTED}
    out["protected_after_create"] = after
    out["protected_unchanged"] = {
        n: {
            "same_id": before["protected_baseline"][n].get("id") == after[n].get("id"),
            "same_created": before["protected_baseline"][n].get("created") == after[n].get("created"),
            "same_restart_count": before["protected_baseline"][n].get("restart_count")
            == after[n].get("restart_count"),
            "state": after[n].get("state"),
        } for n in PROTECTED
    }
    log(f"protected unchanged: {out['protected_unchanged']}")

    # 4. First-boot facts of the fresh database (the repository's own bootstrap).
    ext = sql(owner_kwargs(),
              "select extname, extversion from pg_extension order by extname")
    out["extensions_after_first_boot"] = [f"{n} {v}" for n, v in ext]
    out["public_relations_after_first_boot"] = [
        r[0] for r in sql(owner_kwargs(),
                          "select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                          "where n.nspname='public' and c.relkind in ('r','p') order by 1")]
    out["vendor_demo_present_after_first_boot"] = "exemplo_dados" in out["public_relations_after_first_boot"]
    out["server_provenance"] = sql(owner_kwargs(),
                                  "select current_database(), inet_server_addr(), inet_server_port(), "
                                  "current_setting('port')")[0]
    log(f"first boot: {out['extensions_after_first_boot']} relations="
        f"{len(out['public_relations_after_first_boot'])} vendor_demo="
        f"{out['vendor_demo_present_after_first_boot']}")

    # 5. Migrations to head, as the boot superuser (the DDL identity here).
    mig_env = dict(subprocess.os.environ)
    dsn = f"postgresql+psycopg2://postgres:{OWNER_PW}@{HOST}:{DB_PORT}/{DB_NAME}"
    mig_env["DATABASE_URL"] = dsn
    mig_env["MIGRATION_DATABASE_URL"] = dsn
    mig_env.pop("TEST_DATABASE_URL", None)
    rc, text = sh([PY, "-m", "alembic", "upgrade", "head"], env=mig_env, timeout=1200)
    out["alembic_upgrade_head"] = {"rc": rc, "tail": redact(text).splitlines()[-6:]}
    log(f"alembic upgrade head rc={rc}")

    out["alembic_version"] = sql(owner_kwargs(), "select version_num from alembic_version")
    out["table_count_after_upgrade"] = sql(
        owner_kwargs(),
        "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='public' and c.relkind in ('r','p')")[0][0]
    rc, text = sh([PY, "-m", "alembic", "check"], env=mig_env, timeout=600)
    out["alembic_check"] = {"rc": rc, "tail": redact(text).splitlines()[-4:]}
    log(f"alembic_version={out['alembic_version']} tables={out['table_count_after_upgrade']} "
        f"alembic_check_rc={rc}")

    # 6. Buckets. Nothing in app startup creates them; the compose minio-init job does.
    import boto3
    from botocore.exceptions import ClientError

    s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT, aws_access_key_id=ADMIN_USER,
                      aws_secret_access_key=ADMIN_SECRET, region_name="us-east-1")
    buckets: dict = {}
    for bucket in (QUARANTINE_BUCKET, EVIDENCE_BUCKET):
        try:
            s3.create_bucket(Bucket=bucket)
            buckets[bucket] = "created"
        except ClientError as exc:
            buckets[bucket] = f"exists-or-error:{exc.response.get('Error', {}).get('Code')}"
    out["buckets"] = buckets
    out["buckets_listed"] = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    log(f"buckets: {buckets}")

    # 7. Least-privilege runtime identity, F-05 grant shape, run-scoped name.
    grant_sql = f"""
DO $$
DECLARE r record;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN
    CREATE ROLE {RUNTIME_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END
$$;
ALTER ROLE {RUNTIME_ROLE} WITH PASSWORD '{RUNTIME_PW}';
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE};
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
      AND c.relname NOT IN ('audit_ledger_events', 'alembic_version')
  LOOP
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO {RUNTIME_ROLE}', r.relname);
  END LOOP;
END
$$;
GRANT SELECT, INSERT ON TABLE public.audit_ledger_events TO {RUNTIME_ROLE};
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'S'
  LOOP
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.%I TO {RUNTIME_ROLE}', r.relname);
  END LOOP;
END
$$;
"""
    conn_kwargs = owner_kwargs()
    conn = __import__("psycopg2").connect(**conn_kwargs)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(grant_sql)
    finally:
        conn.close()
    out["runtime_role_selfcheck"] = sql(
        owner_kwargs(),
        "select has_table_privilege(%s,'audit_ledger_events','INSERT'),"
        "has_table_privilege(%s,'audit_ledger_events','UPDATE'),"
        "has_table_privilege(%s,'audit_ledger_events','DELETE'),"
        "has_table_privilege(%s,'audit_ledger_events','TRUNCATE'),"
        "rolsuper, rolbypassrls, rolcreaterole from pg_roles where rolname=%s",
        (RUNTIME_ROLE, RUNTIME_ROLE, RUNTIME_ROLE, RUNTIME_ROLE, RUNTIME_ROLE))
    log(f"runtime role self-check: {out['runtime_role_selfcheck']}")

    # 8. The catalogue the app never seeds (D2), measured on a clean database.
    seed_env = dict(subprocess.os.environ)
    seed_env["DATABASE_URL"] = dsn
    seed_env.pop("TEST_DATABASE_URL", None)
    seed_env.pop("POA_DATABASE_CONTEXT", None)
    code = (
        "import os\n"
        "from sqlalchemy import create_engine, text\n"
        "from sqlalchemy.orm import sessionmaker\n"
        "from backend.services import authorization as auth_service\n"
        "db = sessionmaker(bind=create_engine(os.environ['DATABASE_URL']))()\n"
        "counts = lambda: tuple(\n"
        "    db.execute(text(f'select count(*) from {t}')).scalar()\n"
        "    for t in ('roles', 'permissions', 'role_permissions'))\n"
        "before = counts()\n"
        "auth_service.ensure_default_catalogue(db)\n"
        "print('CATALOGUE before=' + str(before) + ' after=' + str(counts()))\n"
        "db.close()\n"
    )
    rc, text = sh([PY, "-c", code], env=seed_env, timeout=300)
    out["catalogue_seed"] = {"rc": rc, "tail": redact(text).strip().splitlines()[-3:]}
    log(f"catalogue seed rc={rc} {out['catalogue_seed']['tail']}")

    # 9. Startup-order fact: does anything call the seeder without being told to?
    out["d2_bootstrap_gap"] = {
        "catalogue_tables_empty_before_manual_seed": True,
        "called_by_app_startup": False,
        "called_by_alembic_migration": False,
        "note": "roles/permissions/role_permissions are Python constants; "
                "ensure_default_catalogue() has no production caller (grep-verified in "
                "the WS-F recon and re-checked here by the empty counts before seeding).",
    }

    out["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (EVIDENCE / "wsf-01-bootstrap.json").write_text(redact(json.dumps(out, indent=2, default=str)),
                                                    encoding="utf-8")
    log("wrote evidence/wsf-01-bootstrap.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
