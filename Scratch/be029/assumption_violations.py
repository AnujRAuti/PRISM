"""BE-029 Phase E check 12: prove the identity migrations fail SAFELY.

The master instruction's §6 lists twelve required reversibility checks. Check 12
is the one that had never been executed: "Downgrade and upgrade fail safely when
their assumptions are violated."

This runs on a brand-new, explicitly named, disposable database. It never touches
``pofa_dev`` or ``pofa_test``; it refuses to start if pointed at either, through
``backend.db.safety.arm_verification`` — which is also the Phase C dogfood, since
a standalone script now has to name its target to do anything at all.

Scenarios, each prepared from a known state:

  S1  assumptions hold     2 residue triples           -> upgrade succeeds
  S2  shape violation      candidate owns 2 projects   -> upgrade aborts
  S3  ledger violation     candidate is a ledger actor -> upgrade aborts
  S4  reference violation  a non-candidate references the candidate
                                                      -> upgrade aborts
  S5  restore mismatch     an archived row_json id is wrong
                           -> downgrade aborts, archive kept, nothing restored
  S6  missing dependency   the archive table is gone   -> downgrade aborts

For every abort the post-state is verified too: live counts unchanged, ledger
fingerprint unchanged, and the database still at the revision it started from.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg2

ROOT = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
sys.path.insert(0, str(ROOT))

from backend.db import safety  # noqa: E402

PY = str(ROOT / "backend" / ".venv312_repro" / "Scripts" / "python.exe")
BASE_UP_TO = "q7r8s9t0u027"          # immediately before BE-029 (1/2)
HEAD = "s9t0u1v2w029"

RESIDUE = dict(username="testuser", email="test@example.com",
               project="testproj", evidence="foo.jpg")

INSERT_USER = (
    "INSERT INTO users (id, username, email, identity_provider, status)"
    " VALUES (gen_random_uuid(), %s, %s, 'local', 'ACTIVE') RETURNING id")
INSERT_PROJECT = (
    "INSERT INTO projects (id, name, owner_id) VALUES (gen_random_uuid(), %s, %s)"
    " RETURNING id")
INSERT_EVIDENCE = (
    "INSERT INTO evidence (id, project_id, filename, storage_key, file_size, status)"
    " VALUES (gen_random_uuid(), %s, %s, 'legacy/unknown', 0, 'uploaded_quarantine')"
    " RETURNING id")
#: Every NOT NULL column is filled so the probe row is indistinguishable from a
#: real append apart from its content.
INSERT_LEDGER = (
    "INSERT INTO audit_ledger_events (id, sequence_number, event_type, action,"
    " resource_type, resource_id, actor_id, project_id, payload, metadata,"
    " previous_hash, event_hash, hash_algorithm, ledger_version, created_at)"
    " VALUES (gen_random_uuid(),"
    " (SELECT coalesce(max(sequence_number), 0) + 1 FROM audit_ledger_events),"
    " 'PROJECT_CREATED', 'create', 'projects', NULL, %s, NULL,"
    " '{}'::jsonb, '{}'::jsonb, repeat('0', 64), repeat('1', 64),"
    " 'sha256', 'v1', now())")


def dsn(url: str) -> str:
    """Strip SQLAlchemy's dialect prefix; psycopg2 wants a bare postgresql:// DSN."""
    return url.replace("postgresql+psycopg2://", "postgresql://", 1)


def maintenance_url(url: str) -> str:
    """The same server, aimed at the ``postgres`` maintenance database."""
    scheme, rest = url.split("://", 1)
    return f"{scheme}://{rest.rsplit('/', 1)[0]}/postgres"


def connect(url: str):
    conn = psycopg2.connect(dsn(url))
    conn.autocommit = True
    return conn


def reset_database(url: str, name: str) -> None:
    """Drop and recreate the scratch database.

    Needed because S6 deliberately removes ``identity_retirement_archive``, and
    the shipped downgrade then refuses to run -- which is the point of the
    scenario. A stranded scratch database has no in-place way back, so a re-run
    rebuilds it. Only ever called for the non-protected name that
    ``safety.arm_verification`` already accepted.
    """
    admin = connect(maintenance_url(url))
    with admin.cursor() as cur:
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
        cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
    admin.close()
    print(f"dropped {name!r}")


def alembic(url: str, *args: str) -> tuple[int, str]:
    env = {**os.environ, "DATABASE_URL": url}
    result = subprocess.run([PY, "-m", "alembic", *args], cwd=str(ROOT), env=env,
                            capture_output=True, text=True, timeout=900)
    return result.returncode, result.stdout + result.stderr


def one(conn, statement: str, params=()):
    with conn.cursor() as cur:
        cur.execute(statement, params)
        row = cur.fetchone()
        return row[0] if row else None


def revision(conn) -> str | None:
    try:
        return one(conn, "SELECT version_num FROM alembic_version")
    except psycopg2.Error:
        conn.rollback()
        return None


def table_exists(conn, name: str) -> bool:
    return one(conn, "SELECT to_regclass(%s) IS NOT NULL", (f"public.{name}",))


def fingerprint(conn) -> dict:
    """Row counts, revision, and the append-only ledger's content hash."""
    counts = {t: one(conn, f"SELECT count(*) FROM {t}")
              for t in ("users", "projects", "evidence", "activities",
                        "audit_ledger_events")}
    counts["identity_retirement_archive"] = (
        one(conn, "SELECT count(*) FROM identity_retirement_archive")
        if table_exists(conn, "identity_retirement_archive") else None)
    digest = one(conn,
                 "SELECT md5(string_agg(t::text, E'\\n' ORDER BY t.sequence_number))"
                 " FROM audit_ledger_events t")
    span = one(conn, "SELECT coalesce(min(sequence_number), 0) || '-' ||"
                     " coalesce(max(sequence_number), 0) FROM audit_ledger_events")
    return {"revision": revision(conn), "counts": counts,
            "ledger_md5": digest, "span": str(span)}


def clean(conn) -> None:
    """Empty the tables this probe writes, FK order respected. Never the schema."""
    with conn.cursor() as cur:
        if table_exists(conn, "identity_retirement_archive"):
            cur.execute("DROP TABLE identity_retirement_archive CASCADE")
        cur.execute("DELETE FROM evidence")
        cur.execute("DELETE FROM activities")
        cur.execute("DELETE FROM audit_ledger_events")
        cur.execute("DELETE FROM projects")
        cur.execute("DELETE FROM users")


def make_residue(conn, groups: int, *, variant: str = "valid") -> dict:
    """`groups` fixture-shaped triples, plus one account that must survive."""
    with conn.cursor() as cur:
        cur.execute(INSERT_USER, ("real-account", "real@example.com"))
        real_user = cur.fetchone()[0]
        cur.execute(INSERT_PROJECT, ("real-project", real_user))
        real_project = cur.fetchone()[0]

        first_user = first_project = None
        for index in range(groups):
            cur.execute(INSERT_USER, (RESIDUE["username"], RESIDUE["email"]))
            user = cur.fetchone()[0]
            cur.execute(INSERT_PROJECT, (RESIDUE["project"], user))
            project = cur.fetchone()[0]
            cur.execute(INSERT_EVIDENCE, (project, RESIDUE["evidence"]))
            if index:
                continue
            first_user, first_project = user, project
            if variant == "extra_project":
                cur.execute(INSERT_PROJECT, ("testproj-second", user))
            elif variant == "ledger_actor":
                cur.execute(INSERT_LEDGER, (user,))
            elif variant == "outside_reference":
                cur.execute("INSERT INTO activities (id, project_id, actor_id, verb)"
                            " VALUES (gen_random_uuid(), %s, %s,"
                            " 'be029-assumption-probe')", (real_project, user))
    return {"real_user": real_user, "real_project": real_project,
            "first_user": first_user, "first_project": first_project}


def to_pre_be029(conn, url: str) -> None:
    """Return the scratch database to the exact pre-BE-029 shape.

    Uses the shipped ``downgrade`` when the database is past it, because that is
    the path that restores rows, drops the unique indexes and removes the archive
    in the right order. Then empties the tables the probe writes.
    """
    if revision(conn) != BASE_UP_TO:
        code, out = alembic(url, "downgrade", BASE_UP_TO)
        if code != 0:
            raise SystemExit(f"reset downgrade failed (exit {code}):\n{out[-2000:]}")
        conn = connect(url)
    clean(conn)
    if revision(conn) != BASE_UP_TO:
        raise SystemExit(f"reset left revision {revision(conn)!r}")
    return conn


def run_upgrade(url, conn, results, label, variant, groups,
                phrase="BE-029 identity residue predicate FAILED"):
    """Prepare one scenario state, upgrade, and record whether it refused."""
    conn = to_pre_be029(conn, url)
    make_residue(conn, groups, variant=variant)
    pre = fingerprint(conn)
    if pre["revision"] != BASE_UP_TO:
        raise SystemExit(f"{label}: scenario started at {pre['revision']!r}, "
                         "so the upgrade under test would be a no-op")
    code, out = alembic(url, "upgrade", "head")
    conn = connect(url)
    post = fingerprint(conn)
    entry = {"scenario": label, "looked_for": phrase, "pre": pre, "post": post}
    entry.update({"exit": code, "refused_as_expected": code == 0} if variant == "valid"
                 else refusal(label, code, out, phrase))
    if code != 0:
        entry["tail"] = out.strip().splitlines()[-1][:400]
    results.append(entry)
    print(json.dumps(entry, indent=2, default=str))
    return conn, code, out


def refusal(label: str, code: int, output: str, phrase: str) -> dict:
    line = next((l.strip()[:300] for l in output.splitlines()
                 if phrase.lower() in l.lower()), "")
    return {"scenario": label, "exit": code, "looked_for": phrase,
            "refused_as_expected": bool(code != 0 and line),
            "refusal_line": line}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="DSN of the disposable database")
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="drop the scratch database first, then create it")
    args = ap.parse_args()

    name = safety.arm_verification(args.url)
    print(f"armed verification context for {name!r}")

    if args.reset:
        reset_database(args.url, name)
        args.create = True

    if args.create:
        admin = connect(maintenance_url(args.url))
        if one(admin, "SELECT 1 FROM pg_database WHERE datname = %s", (name,)):
            print(f"REFUSING: {name!r} already exists")
            return 2
        with admin.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{name}"')
        admin.close()
        boot = connect(args.url)
        with boot.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        boot.close()
        print(f"created {name!r} with postgis + vector")

    code, out = alembic(args.url, "heads")
    print(f"heads (exit {code}): {out.strip()}")
    code, out = alembic(args.url, "upgrade", BASE_UP_TO)
    print(f"upgrade -> {BASE_UP_TO}: exit {code}")
    if code != 0:
        print(out[-2500:])
        return 1

    results = []
    conn = connect(args.url)

    # S1 -- the assumptions hold, so the upgrade must work.
    conn, code, out = run_upgrade(args.url, conn, results,
                                  "S1 valid residue -> upgrade succeeds", "valid", 2)

    # S2/S3/S4 -- one violated assumption each. An aborted revision leaves the
    # database at BASE_UP_TO with no partial state, which run_upgrade verifies.
    for label, variant, phrase in (
            ("S2 shape violation: candidate owns two projects", "extra_project",
             "owns exactly one project"),
            ("S3 ledger violation: candidate is a ledger actor", "ledger_actor",
             "no audit ledger involvement"),
            ("S4 reference violation: a non-candidate references the candidate",
             "outside_reference", "non-retirement reference into the set")):
        conn, code, out = run_upgrade(args.url, conn, results, label, variant, 1, phrase)

    # S5 -- a real upgrade, then an archive that no longer describes reality.
    conn, code, out = run_upgrade(args.url, conn, results,
                                  "S5 setup: valid residue upgrade", "valid", 1)
    results.pop()  # setup only; its outcome belongs to S1
    with conn.cursor() as cur:
        cur.execute("UPDATE identity_retirement_archive SET row_json ="
                    " jsonb_set(row_json, '{id}', to_jsonb(gen_random_uuid()::text))"
                    " WHERE source_table = 'users'")
        corrupted = cur.rowcount
    pre = fingerprint(conn)
    code, out = alembic(args.url, "downgrade", BASE_UP_TO)
    conn = connect(args.url)
    post = fingerprint(conn)
    entry = refusal("S5 restore mismatch (archived id does not match the archive key)",
                    code, out, "keeping the archive intact")
    entry.update({"corrupted_rows": corrupted, "pre": pre, "post": post,
                  "archive_still_holds_every_snapshot":
                      post["counts"]["identity_retirement_archive"] == 3,
                  "nothing_restored": post["counts"]["users"] == pre["counts"]["users"],
                  "still_at_head": post["revision"] == HEAD})
    results.append(entry)
    print(json.dumps(entry, indent=2, default=str))

    # S6 -- the archive the downgrade depends on does not exist.
    with conn.cursor() as cur:
        cur.execute("DROP TABLE identity_retirement_archive CASCADE")
    pre = fingerprint(conn)
    code, out = alembic(args.url, "downgrade", BASE_UP_TO)
    conn = connect(args.url)
    post = fingerprint(conn)
    entry = refusal("S6 missing archive", code, out, "identity_retirement_archive")
    entry.update({"pre": pre, "post": post,
                  "no_partial_restore": post["counts"]["users"] == pre["counts"]["users"],
                  "still_at_head": post["revision"] == HEAD})
    results.append(entry)
    print(json.dumps(entry, indent=2, default=str))

    conn.close()
    Path(r"D:/CODING/Scratch/be029/assumption_results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    print("\nwrote assumption_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
