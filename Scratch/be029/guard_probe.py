"""BE-029 scratch: prove the residue predicate ABORTs a non-residue candidate.

Runs against the disposable pofa_be029_fresh database. For each scenario it
downgrades to q7r8s9t0u027 (the BE-029 parent), fabricates one "looks like
residue" triple, attempts `alembic upgrade head`, and requires:

  1. the migration fails, reporting the named guard finding;
  2. nothing changed: still at q7r8s9t0u027, the inserted rows still present,
     no archive table left behind -- the abort is transactional, so a blocked
     candidate is never half-retired.

Scenarios (one per predicate family):
  shape      -- the candidate owns a project that is NOT named testproj
  reference  -- a proper triple, but a claims row references the user
  ledger     -- a proper triple, but an audit_ledger_events row names the user
  empty      -- no residue at all (the fresh-from-base path), must succeed
"""
import os
import subprocess
import sys
import uuid

import psycopg2

DB = "pofa_be029_fresh"
URL = f"postgresql://postgres:postgres@localhost:5432/{DB}"
ENV = dict(os.environ, DATABASE_URL=URL)
PY = sys.executable
REPO = r"D:/CODING/Projects/Proof-Of-Action-Final"
PARENT = "q7r8s9t0u027"
HEAD = "s9t0u1v2w029"


def alembic(*args):
    proc = subprocess.run([PY, "-m", "alembic", *args], cwd=REPO, env=ENV,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def probe_sql(query, params=()):
    con = psycopg2.connect(URL); con.autocommit = True
    try:
        with con.cursor() as cur:
            cur.execute(query, params)
            try:
                return cur.fetchall()
            except psycopg2.ProgrammingError:
                return None
    finally:
        con.close()


def counts():
    out = {}
    for table in ("users", "projects", "evidence", "claims", "audit_ledger_events"):
        out[table] = probe_sql(f"SELECT count(*) FROM {table}")[0][0]
    return out


def state():
    revision = probe_sql("SELECT version_num FROM alembic_version")[0][0]
    archive = bool(probe_sql("SELECT 1 FROM pg_class WHERE relname ="
                             " 'identity_retirement_archive'"))
    archived = (probe_sql("SELECT count(*) FROM identity_retirement_archive")[0][0]
                 if archive else None)
    return revision, archived


def fresh_parent():
    """Return the database to the BE-029 parent with no candidate rows at all."""
    code, output = alembic("downgrade", PARENT)
    assert code == 0, output
    probe_sql("DELETE FROM audit_ledger_events")
    probe_sql("DELETE FROM claims")
    probe_sql("DELETE FROM evidence")
    probe_sql("DELETE FROM projects")
    probe_sql("DELETE FROM users")
    return state()


def add_triple(project_name="testproj", with_claim=False, with_ledger=False):
    subject = str(uuid.uuid4())
    user_id = probe_sql(
        "INSERT INTO users (id, username, email, is_active, status, identity_provider,"
        " external_subject, created_at, updated_at)"
        " VALUES (%s, 'testuser', 'test@example.com', true, 'ACTIVE', 'local', %s,"
        " now(), now()) RETURNING id", (subject, subject))
    user_id = user_id[0][0]
    project_id = probe_sql(
        "INSERT INTO projects (id, name, owner_id, created_at)"
        " VALUES (%s, %s, %s, now()) RETURNING id",
        (str(uuid.uuid4()), project_name, user_id))[0][0]
    probe_sql(
        "INSERT INTO evidence (id, project_id, filename, storage_key, file_size, status,"
        " created_at) VALUES (%s, %s, 'foo.jpg', 'legacy/unknown', 0,"
        " 'uploaded_quarantine', now())", (str(uuid.uuid4()), project_id))
    if with_claim:
        probe_sql(
            "INSERT INTO claims (id, project_id, claimant_id, title, description, created_at)"
            " VALUES (%s, %s, %s, 'guard probe', 'fabricated for BE-029 abort testing',"
            " now())", (str(uuid.uuid4()), project_id, user_id))
    if with_ledger:
        probe_sql(
            "INSERT INTO audit_ledger_events (id, sequence_number, event_type, action,"
            " resource_type, resource_id, actor_id, previous_hash, event_hash, created_at)"
            " VALUES (%s, 1, 'USER_CREATED', 'create', 'users', %s, %s, 'x', 'y', now())",
            (str(uuid.uuid4()), user_id, user_id))
    return user_id


def run_case(name, expect_fragment, **kwargs):
    revision, archived = fresh_parent()
    add_triple(**kwargs)
    before = counts()
    code, output = alembic("upgrade", "head")
    revision_after, archived_after = state()
    after = counts()
    findings = [ln.strip() for ln in output.splitlines()
                if "  - " in ln or "predicate FAILED" in ln]
    aborted = code != 0 and expect_fragment in output
    untouched = revision_after == PARENT and archived_after is None and after == before
    print(f"\n=== {name}")
    print(f"    parent={revision} exit={code}")
    print(f"    after: revision={revision_after} archive_present={archived_after is not None}")
    print(f"    rows before={before}")
    print(f"    rows after ={after}")
    for ln in findings[:6]:
        print(f"    | {ln}")
    print(f"    ASSERT aborted_with_expected_finding={aborted}"
          f" fully_rolled_back={untouched} -> "
          f"{'PASS' if aborted and untouched else 'FAIL'}")
    return aborted and untouched


def main():
    results = [
        run_case("shape violation: candidate project is not named testproj",
                 "that project is named testproj", project_name="important-case"),
        run_case("external reference: a claims row names the candidate user",
                 "non-retirement reference into the set: users: claims.claimant_id",
                 with_claim=True),
        run_case("audit ledger: a ledger event names the candidate user",
                 "no audit ledger involvement", with_ledger=True),
    ]

    revision, _ = fresh_parent()
    code, output = alembic("upgrade", "head")
    revision_after, archived = state()
    ok = code == 0 and revision_after == HEAD and archived == 0
    print(f"\n=== empty path (no residue at all, fresh-from-base shape)")
    print(f"    parent={revision} exit={code} head={revision_after}"
          f" archive_rows={archived} -> {'PASS' if ok else 'FAIL'}")
    results.append(ok)

    print("\nGUARD PROBE:", "PASS" if all(results) else "FAIL")
    sys.exit(0 if all(results) else 1)


main()
