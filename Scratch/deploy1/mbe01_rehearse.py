"""M-BE-01 step 8: rehearse the production migration and deployment sequence in isolation.

Nothing here touches `poa_prod`. The rehearsal target is a disposable database
restored from the owner-verified off-host copy of the last production dump
(`D:/CODING/Backups/poa/poa_prod-20261017T153144Z.dump`, 270 156 bytes, sha256
prefix `09c51a3b`, restore-proven on the VM before it was copied off-host). That
is the only way to measure the real sequence -- migrate, verify, fail, recover --
against production-shaped data without writing to production.

The sequence being rehearsed is the one step 10 will execute for real:

  1. restore the dump and confirm the starting revision and vocabulary;
  2. `alembic upgrade head` -- forward only, never `--stamp`;
  3. re-measure: revision, 97-value event vocabulary, every table's row count
     unchanged, `alembic check` reporting no drift;
  4. failure handling: attempt the documented rollback (`alembic downgrade -1`)
     and confirm it refuses *without* damaging the schema, then confirm the
     upgrade is idempotent, which is what a re-run after any interruption needs.

The dump was produced as `poa_owner` on the VM; those roles do not exist on this
laptop's cluster, so the restore runs with --no-owner/--no-privileges. That is a
fidelity limitation of the rehearsal, not of the migration: the schema objects
that carry the rules -- tables, the append-only triggers, the event-type CHECK --
are all inside the dump and are restored.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
PY = REPO / "backend" / ".venv312_repro" / "Scripts" / "python.exe"
DUMP = Path(r"D:/CODING/Backups/poa/poa_prod-20261017T153144Z.dump")
EXPECTED_SHA_PREFIX = "09c51a3b"
CONTAINER = "pofa_db"
ADMIN = "postgres"
TARGET = "poa_disp_prod"
HEAD = "w3x4y5z6a033"
START = "v2w3x4y5z032"


def sh(args: list[str], *, stdin: bytes | None = None, check: bool = True,
       env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=True, input=stdin, env=env,
                          cwd=str(cwd) if cwd else None)
    out = (proc.stdout or b"").decode(errors="replace")
    err = (proc.stderr or b"").decode(errors="replace")
    if check and proc.returncode:
        raise SystemExit(f"{args[:4]} -> rc={proc.returncode}\n{(err or out)[-800:]}")
    return proc


def sql(statement: str, database: str = TARGET) -> str:
    return sh(["docker", "exec", CONTAINER, "psql", "-U", ADMIN, "-d", database,
               "-v", "ON_ERROR_STOP=1", "-tAc", statement]).stdout.decode().strip()


def vocabulary(database: str = TARGET) -> tuple[int, bool]:
    definition = sql("select pg_get_constraintdef(oid) from pg_constraint "
                     "where conname='ck_audit_ledger_event_type_domain'")
    values = (definition.count("'") // 2) if "'" in definition else 0
    return values, "PROJECT_CREATED" in definition


def row_counts(database: str = TARGET) -> dict[str, int]:
    tables = sql("select string_agg(table_name, ',') from information_schema.tables "
                 "where table_schema='public' and table_type='BASE TABLE'").split(",")
    return {t: int(sql(f"select count(*) from public.{t}", database)) for t in tables}


def alembic(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ,
           "DATABASE_URL": f"postgresql+psycopg2://{ADMIN}:postgres@localhost:5432/{TARGET}"}
    return sh([str(PY), "-m", "alembic", *args], check=False, env=env, cwd=REPO)


def main() -> int:
    digest = hashlib.sha256(DUMP.read_bytes()).hexdigest()
    size = DUMP.stat().st_size
    print(f"dump           : {DUMP.name} {size} bytes sha256={digest[:32]}")
    assert digest.startswith(EXPECTED_SHA_PREFIX), "the off-host copy changed"

    sh(["docker", "exec", CONTAINER, "dropdb", "-U", ADMIN, "--if-exists", TARGET])
    sh(["docker", "exec", CONTAINER, "createdb", "-U", ADMIN, TARGET])
    proc = sh(["docker", "exec", "-i", CONTAINER, "pg_restore", "-U", ADMIN,
               "-d", TARGET, "--no-owner", "--no-privileges", "--exit-on-error"],
              stdin=DUMP.read_bytes(), check=False)
    print(f"pg_restore     : rc={proc.returncode}")
    if proc.returncode:
        print((proc.stderr.decode() or proc.stdout.decode())[-1200:])
        return 1

    revision = sql("select version_num from alembic_version")
    types, has_project_created = vocabulary()
    before = row_counts()
    print(f"start          : revision={revision} base_tables={len(before)} "
          f"vocabulary={types} PROJECT_CREATED={has_project_created} "
          f"ledger_rows={before.get('audit_ledger_events')} "
          f"projects={before.get('projects')} evidence={before.get('evidence')}")
    if revision != START:
        raise SystemExit(f"unexpected start revision {revision!r}; rehearsal does not "
                         f"match the production position")

    upgrade = alembic("upgrade", "head")
    print("alembic upgrade head -> " + (upgrade.stdout.decode() or upgrade.stderr.decode())
          .strip().replace("\n", " | ")[-300:])
    if upgrade.returncode:
        return 1

    after = row_counts()
    types_after, has_project_created_after = vocabulary()
    print(f"after          : revision={sql('select version_num from alembic_version')} "
          f"vocabulary={types_after} PROJECT_CREATED={has_project_created_after}")
    changed = {t: (n, after[t]) for t, n in before.items() if n != after[t]}
    lost = {t: n for t, n in after.items() if t not in before}
    print(f"row counts     : {len(before) - len(changed)}/{len(before)} identical, "
          f"changed={changed or 'none'}, new tables={lost or 'none'}")

    check = alembic("check")
    print("alembic check  : rc=%d %s" % (check.returncode,
          (check.stdout.decode() + check.stderr.decode()).strip().replace("\n", " | ")[-300:]))

    print("\nFAILURE HANDLING")
    down = alembic("downgrade", "-1")
    down_text = (down.stdout.decode() + down.stderr.decode()).strip().replace("\n", " | ")
    print(f"alembic downgrade -1 -> rc={down.returncode} {down_text[-260:]}")
    print(f"schema after refusal  : revision={sql('select version_num from alembic_version')} "
          f"vocabulary={vocabulary()[0]} ledger_rows={sql('select count(*) from audit_ledger_events')}")
    again = alembic("upgrade", "head")
    print(f"re-run upgrade (idempotent) -> rc={again.returncode} "
          f"revision={sql('select version_num from alembic_version')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
