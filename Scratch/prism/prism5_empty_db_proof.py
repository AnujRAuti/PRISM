"""PRISM-5: prove the migration chain builds the schema from a genuinely empty database.

A suite that passes against an already-migrated database does not prove that a
fresh production database can be created.  This script creates a new database,
verifies it really is empty, runs the chain to head, checks what came out and
runs the drift check.  It then measures the rollback contract: `downgrade base`
is *refused by design* at the append-only audit-vocabulary revisions, so the
schema stays at head and the release consequence is restore-from-backup.
Determinism is proven the only way that means something here - by rebuilding a
second schema from nothing and comparing structural digests, not table counts.

Nothing here touches pofa_dev or pofa_test: the database is named poa_prism5_*
and dropped at the end.  No connection string is printed.
"""

from __future__ import annotations

import re
import subprocess
import sys

DB = "poa_prism5_empty"
HEAD = "w3x4y5z6a033"
CONTAINER = "pofa_db"
REPO = r"D:/CODING/Projects/Proof-Of-Action-Final"
PYTHON = f"{REPO}/backend/.venv312_repro/Scripts/python.exe"

# Launched as a script, only this file's directory is importable; the catalogue
# comparison below needs the repo's own package.
sys.path.insert(0, REPO)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")


def sh(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True, env=env)


def compose_default(key: str, default: str) -> str:
    text = open(f"{REPO}/docker-compose.yml", encoding="utf-8").read()
    match = re.search(rf"^\s*{key}:\s*\$\{{{key}:-([^}}]*)\}}", text, re.MULTILINE)
    return match.group(1) if match else default


USER = compose_default("POSTGRES_USER", "postgres")


def psql(database: str, statement: str) -> str:
    proc = sh(["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", database,
               "-tAc", statement])
    if proc.returncode:
        raise SystemExit(f"psql on {database} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


def dsn() -> str:
    return f"postgresql+psycopg2://{USER}:{compose_default('POSTGRES_PASSWORD', 'postgres')}@localhost:5432/{DB}"


def alembic(*arguments: str) -> tuple[int, str]:
    env = {**subprocess.os.environ, "DATABASE_URL": dsn()}
    proc = sh([PYTHON, "-m", "alembic", *arguments], env=env)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def table_count() -> int:
    return int(psql(DB, "select count(*) from information_schema.tables "
                        "where table_schema='public' and table_type='BASE TABLE'"))


#: Revisions whose downgrade() raises on purpose. The authoritative list is
#: pinned by tests/unit/test_migrations.py; this is the release consequence of
#: it, so rollback past head is a restore-from-backup.
REFUSING_REVISIONS = frozenset({"v2w3x4y5z032", "w3x4y5z6a033"})


def digest(query: str) -> str:
    return psql(DB, query) or "(empty)"


def schema_digest() -> dict[str, str]:
    """Fingerprint the schema's structure, not its size.

    A count comparison would call two builds identical while one lost a
    nullable flag, a CHECK, an index or an append-only trigger, so each of
    those is folded into its own digest.
    """
    return {
        "tables": digest(
            "select count(*) from information_schema.tables "
            "where table_schema='public' and table_type='BASE TABLE'"),
        "columns": digest(
            "select md5(string_agg(s, chr(31) order by s)) from ("
            "  select table_name||'.'||column_name||'|'||coalesce(udt_name, data_type)"
            "||'|'||is_nullable||'|'||coalesce(column_default,'') as s"
            "  from information_schema.columns where table_schema='public') t"),
        "constraints": digest(
            "select md5(string_agg(s, chr(31) order by s)) from ("
            "  select r.relname||'|'||c.conname||'|'||pg_get_constraintdef(c.oid) as s"
            "  from pg_constraint c"
            "  join pg_class r on r.oid = c.conrelid"
            "  join pg_namespace n on n.oid = r.relnamespace"
            "  where n.nspname='public') t"),
        "indexes": digest(
            "select md5(string_agg(s, chr(31) order by s)) from ("
            "  select tablename||'|'||indexname||'|'||indexdef as s"
            "  from pg_indexes where schemaname='public') t"),
        # Ordinary functions only: pg_get_functiondef raises for the PostGIS
        # aggregates in this schema, and none of them are created by a revision.
        "routines": digest(
            "select md5(string_agg(s, chr(31) order by s)) from ("
            "  select p.proname||'|'||pg_get_functiondef(p.oid) as s"
            "  from pg_proc p join pg_namespace n on n.oid = p.pronamespace"
            "  where n.nspname='public' and p.prokind = 'f') t"),
        "triggers": digest(
            "select md5(string_agg(s, chr(31) order by s)) from ("
            "  select r.relname||'|'||t.tgname||'|'||pg_get_triggerdef(t.oid) as s"
            "  from pg_trigger t join pg_class r on r.oid = t.tgrelid"
            "  join pg_namespace n on n.oid = r.relnamespace"
            "  where n.nspname='public' and not t.tgisinternal) t"),
        "types": digest(
            "select count(*) from pg_type ty"
            " join pg_namespace n on n.oid = ty.typnamespace"
            " where n.nspname='public'"),
    }


def recreate() -> None:
    psql("postgres", f"drop database {DB} with (force)")
    psql("postgres", f"create database {DB}")


def schema_counts() -> str:
    """Plain numbers for the evidence record, alongside the digests."""
    queries = [
        ("columns", "select count(*) from information_schema.columns"
                    " where table_schema='public'"),
        ("constraints", "select count(*) from pg_constraint c"
                        " join pg_class r on r.oid = c.conrelid"
                        " join pg_namespace n on n.oid = r.relnamespace"
                        " where n.nspname='public'"),
        ("indexes", "select count(*) from pg_indexes where schemaname='public'"),
        ("routines", "select count(*) from pg_proc p"
                     " join pg_namespace n on n.oid = p.pronamespace"
                     " where n.nspname='public' and p.prokind='f'"),
        ("triggers", "select count(*) from pg_trigger t"
                     " join pg_class r on r.oid = t.tgrelid"
                     " join pg_namespace n on n.oid = r.relnamespace"
                     " where n.nspname='public' and not t.tgisinternal"),
    ]
    return ", ".join(f"{label} {psql(DB, query)}" for label, query in queries)


def run_checks() -> int:
    exists = psql("postgres", f"select 1 from pg_database where datname='{DB}'")
    if exists:
        psql("postgres", f"drop database {DB} with (force)")
    psql("postgres", f"create database {DB}")
    print(f"created {DB} on the local postgres container")

    before = table_count()
    check("starts empty", before == 0, f"{before} base tables before any migration")

    code, output = alembic("upgrade", "head")
    check("upgrade head runs", code == 0,
          output.splitlines()[-1] if output else "(no output)")
    if code != 0:
        return 1

    revision = psql(DB, "select version_num from alembic_version")
    check("lands on the single head", revision == HEAD, f"alembic_version = {revision}")

    after = table_count()
    check("schema built from nothing", after > 0, f"{after} base tables after migration")

    extensions = sorted(psql(DB, "select extname from pg_extension order by 1").splitlines())
    check("required extensions", {"postgis", "vector"} <= set(extensions),
          f"extensions = {', '.join(extensions)}")

    roles = int(psql(DB, "select count(*) from roles"))
    permissions = int(psql(DB, "select count(*) from permissions"))
    grants = int(psql(DB, "select count(*) from role_permissions"))
    from backend.db.models import AUTH_PERMISSIONS, AUTH_ROLE_PERMISSIONS, AUTH_ROLES
    expected_grants = sum(len(v) for v in AUTH_ROLE_PERMISSIONS.values())
    check("authorization catalogue is seeded",
          roles == len(AUTH_ROLES) and permissions == len(AUTH_PERMISSIONS)
          and grants == expected_grants,
          f"roles {roles}/{len(AUTH_ROLES)}, permissions {permissions}/{len(AUTH_PERMISSIONS)}, "
          f"grants {grants}/{expected_grants}")

    code, output = alembic("check")
    check("no autogenerate drift on the fresh schema", code == 0,
          " | ".join(line.strip() for line in output.splitlines()[-3:]) or "(no output)")

    code, output = alembic("downgrade", "base")
    after_refusal = table_count()
    current = psql(DB, "select version_num from alembic_version")
    refused = "cannot downgrade an append-only audit vocabulary" in output
    check("downgrade base refuses atomically at the append-only vocabulary",
          code != 0 and refused and after_refusal == after and current == HEAD,
          f"rc={code}, refusal message present={refused}, {after_refusal} base tables "
          f"still present, alembic_version still {current}")
    print("NOTE  rollback past "
          f"{', '.join(sorted(REFUSING_REVISIONS))} is restore-from-backup, "
          "not `alembic downgrade`.")

    # Determinism has to mean "a second schema built from nothing matches", not
    # "the schema that never went away looks the same".  Rebuild from an empty
    # database and compare structure, not just a table count.
    digest_a = schema_digest()
    recreate()
    code, _ = alembic("upgrade", "head")
    digest_b = schema_digest()
    differences = [k for k in digest_a if digest_a[k] != digest_b[k]]
    rebuilt = int(digest_b["tables"])
    check("rebuild from empty is deterministic",
          code == 0 and not differences and rebuilt == after,
          f"{schema_counts()}, {rebuilt} base tables vs {after}, "
          f"digests match ({'all equal' if not differences else 'differ: ' + ', '.join(differences)})")

    psql("postgres", f"drop database {DB} with (force)")
    gone = psql("postgres", f"select 1 from pg_database where datname='{DB}'")
    check("disposable database dropped", gone == "", "database no longer exists")

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n--- {len(results) - len(failed)} passed, {len(failed)} failed"
          f"{' (' + ', '.join(failed) + ')' if failed else ''} ---")
    return 1 if failed else 0


def drop_disposable_database() -> None:
    sh(["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", "postgres", "-tAc",
        f"drop database if exists {DB} with (force)"])


if __name__ == "__main__":
    try:
        sys.exit(run_checks())
    finally:
        drop_disposable_database()
