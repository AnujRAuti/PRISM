"""BE-029 G3 Phase 1 / Phase 3 preflight: prove live pofa_dev still matches the
target set that was reviewed and approved, using the migration's OWN predicate,
read-only.

Usage: python preflight_live.py <url> <expected_db> <expected_revision> \
                                <reviewed_snapshot.json> <outfile>

Exits non-zero on any deviation, so it can gate the migration.

Checks, all SELECT-only:
  1. current_database() is the expected database (never trust DATABASE_URL).
  2. alembic revision is the expected parent revision, and there is exactly one row.
  3. the candidate set (users / projects / evidence) is the reviewed set: same ids,
     same size, 1:1:1 linkage.
  4. the five shape checks from r8s9t0u1v028 return zero violations.
  5. every foreign key in the catalog pointing at users/projects/evidence is either
     inside the retirement set (the two known self-references) or empty; a composite
     key is a hard stop, as in the migration.
  6. no audit_ledger_events row names a candidate as actor, project or resource, and
     the ledger count is recorded.
  7. the only duplicate username/email groups are the synthetic fixture values.
  8. identity_retirement_archive does not exist yet.
  9. row counts for every table in public, so a later comparison can prove nothing
     unrelated moved.
"""
import json
import re
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

URL, EXPECT_DB, EXPECT_REV, REVIEWED, OUT = sys.argv[1:6]

RESIDUE_USERNAME = "testuser"
RESIDUE_EMAIL = "test@example.com"
RESIDUE_PROJECT_NAME = "testproj"
RESIDUE_EVIDENCE_FILENAME = "foo.jpg"

WITH_CTES = (
    "WITH cand_users AS (SELECT u.id FROM users u WHERE u.username ="
    f" '{RESIDUE_USERNAME}' AND u.email = '{RESIDUE_EMAIL}'),"
    " cand_projects AS (SELECT p.id FROM projects p WHERE p.owner_id IN"
    " (SELECT id FROM cand_users)),"
    " cand_evidence AS (SELECT e.id FROM evidence e WHERE e.project_id IN"
    " (SELECT id FROM cand_projects)"
    f" AND e.filename = '{RESIDUE_EVIDENCE_FILENAME}')")

IDS = {
    "users": f"{WITH_CTES} SELECT id FROM cand_users ORDER BY id",
    "projects": f"{WITH_CTES} SELECT id FROM cand_projects ORDER BY id",
    "evidence": f"{WITH_CTES} SELECT id FROM cand_evidence ORDER BY id",
}

SHAPE = (
    ("owns exactly one project",
     f"{WITH_CTES} SELECT count(*) FROM cand_users cu WHERE"
     " (SELECT count(*) FROM projects p WHERE p.owner_id = cu.id) <> 1"),
    ("that project is named testproj",
     f"{WITH_CTES} SELECT count(*) FROM cand_projects cp WHERE NOT EXISTS"
     f" (SELECT 1 FROM projects p WHERE p.id = cp.id AND p.name ="
     f" '{RESIDUE_PROJECT_NAME}')"),
    ("every candidate project holds evidence",
     f"{WITH_CTES} SELECT count(*) FROM cand_projects cp WHERE"
     " (SELECT count(*) FROM evidence e WHERE e.project_id = cp.id) < 1"),
    ("every child of a candidate project is foo.jpg",
     f"{WITH_CTES} SELECT count(*) FROM evidence e WHERE e.project_id IN"
     f" (SELECT id FROM cand_projects) AND e.filename <>"
     f" '{RESIDUE_EVIDENCE_FILENAME}'"),
    ("no audit ledger involvement (actor, project or resource)",
     f"{WITH_CTES} SELECT count(*) FROM audit_ledger_events l WHERE"
     " l.actor_id IN (SELECT id FROM cand_users)"
     " OR l.project_id IN (SELECT id FROM cand_projects)"
     " OR l.resource_id IN (SELECT id FROM cand_users UNION"
     "                     SELECT id FROM cand_projects UNION"
     "                     SELECT id FROM cand_evidence)"),
)

FK_SQL = """
SELECT cl.relname AS table_name, a.attname AS column_name,
       array_length(c.conkey, 1) AS arity
FROM pg_constraint c
JOIN pg_class cl ON cl.oid = c.conrelid
JOIN pg_namespace ns ON ns.oid = cl.relnamespace
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
WHERE c.contype = 'f' AND ns.nspname = 'public'
  AND c.confrelid = {ref}::regclass
ORDER BY 1, 2
"""
EXCLUDED = {("projects", "owner_id"), ("evidence", "project_id")}
SOURCES = {"users": ("users", "cand_users"),
           "projects": ("projects", "cand_projects"),
           "evidence": ("evidence", "cand_evidence")}

problems = []
report = {}
conn = psycopg2.connect(URL)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=RealDictCursor)


def one(sql):
    cur.execute(sql)
    return cur.fetchone()


def scalar(sql):
    row = one(sql)
    return list(row.values())[0]


# 1 + 2 ------------------------------------------------------------------
db = scalar("SELECT current_database()")
report["current_database"] = db
if db != EXPECT_DB:
    problems.append(f"connected to {db}, expected {EXPECT_DB} — REFUSING to continue")
cur.execute("SELECT version_num FROM alembic_version")
versions = [r["version_num"] for r in cur.fetchall()]
report["alembic_versions"] = versions
if versions != [EXPECT_REV]:
    problems.append(f"alembic_version is {versions}, expected exactly ['{EXPECT_REV}']")

# 3 ----------------------------------------------------------------------
reviewed = json.load(open(REVIEWED))["snapshot"]
candidates = {}
for table, sql in IDS.items():
    cur.execute(sql)
    candidates[table] = [str(r["id"]) for r in cur.fetchall()]
    report[f"{table}_candidate_count"] = len(candidates[table])
    ref = sorted(str(x["id"]) for x in reviewed[table])
    if candidates[table] != ref:
        missing = sorted(set(ref) - set(candidates[table]))
        extra = sorted(set(candidates[table]) - set(ref))
        problems.append(f"{table} candidate set differs from the reviewed set:"
                        f" missing={missing} new={extra}")
if not (len(candidates["users"]) == len(candidates["projects"])
        == len(candidates["evidence"])):
    problems.append(f"candidate sets are not 1:1:1: {len(candidates['users'])}"
                    f" / {len(candidates['projects'])} / {len(candidates['evidence'])}")
report["candidates"] = candidates

# 4 ----------------------------------------------------------------------
for description, sql in SHAPE:
    violations = int(scalar(sql))
    report[f"shape::{description}"] = violations
    if violations:
        problems.append(f"shape check FAILED — {description}: {violations} violating row(s)")

# 5 ----------------------------------------------------------------------
for source_table, (ref_table, cte) in SOURCES.items():
    cur.execute(FK_SQL.format(ref=f"'{ref_table}'"))
    for row in cur.fetchall():
        ref = f"{row['table_name']}.{row['column_name']}->{ref_table}"
        count_sql = (f"{WITH_CTES} SELECT count(*) FROM \"{row['table_name']}\" t"
                     f" WHERE t.\"{row['column_name']}\" IN (SELECT id FROM {cte})")
        if row["arity"] is None or int(row["arity"]) > 1:
            problems.append(f"composite FK {ref}: the predicate cannot evaluate it"
                            " column-by-column")
            continue
        if (row["table_name"], row["column_name"]) in EXCLUDED:
            report.setdefault("fk_in_set", []).append(f"{ref} = {int(scalar(count_sql))}")
            continue
        count = int(scalar(count_sql))
        report[f"fk_out_of_set::{ref}"] = count
        if count:
            problems.append(f"NEW reference into the retirement set: {ref} = {count}")

# 6 ----------------------------------------------------------------------
report["audit_ledger_events"] = int(scalar("SELECT count(*) FROM audit_ledger_events"))
report["ledger_min_max_sequence"] = [
    int(scalar("SELECT min(sequence_number) FROM audit_ledger_events")),
    int(scalar("SELECT max(sequence_number) FROM audit_ledger_events"))]

# 7 ----------------------------------------------------------------------
for column, expected_value in (("username", RESIDUE_USERNAME), ("email", RESIDUE_EMAIL)):
    cur.execute(f"SELECT {column} AS v, count(*) AS n FROM users GROUP BY {column}"
                " HAVING count(*) > 1 ORDER BY 1")
    groups = [dict(r) for r in cur.fetchall()]
    report[f"dup_{column}_groups"] = groups
    if groups != [{"v": expected_value, "n": len(candidates["users"])}]:
        problems.append(f"duplicate {column} groups are not the single reviewed"
                        f" synthetic group of {len(candidates['users'])}:"
                        f" {groups}")
    # nothing outside the candidate set may carry the fixture identity either
    outside = int(scalar(
        f"{WITH_CTES} SELECT count(*) FROM users WHERE {column} = '{expected_value}'"
        " AND id NOT IN (SELECT id FROM cand_users)"))
    report[f"{column}_outside_candidate_set"] = outside
    if outside:
        problems.append(f"{outside} row(s) carry {column}='{expected_value}' but are not"
                        " in the candidate set — the retirement set is not closed")

# 8 ----------------------------------------------------------------------
report["identity_retirement_archive_present"] = bool(
    int(scalar("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace"
               " WHERE n.nspname='public' AND c.relname='identity_retirement_archive'")))
if report["identity_retirement_archive_present"]:
    problems.append("identity_retirement_archive already exists — the migration may have"
                    " run partially; refusing to proceed")

# 9 ----------------------------------------------------------------------
cur.execute("SELECT c.relname AS t FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace"
            " WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY 1")
tables = [r["t"] for r in cur.fetchall()]
counts, fingerprints = {}, {}
for t in tables:
    counts[t] = int(scalar(f'SELECT count(*) FROM "public"."{t}"'))
    fingerprints[t] = one(f'SELECT md5(string_agg(x::text, E\'\\n\' ORDER BY x::text)) AS fp'
                          f' FROM "public"."{t}" x')["fp"]
report["table_counts"] = counts
report["table_fingerprints"] = fingerprints
conn.close()

json.dump(report, open(OUT, "w"), indent=1, default=str)

print(f"database          : {report['current_database']}")
print(f"revision          : {report['alembic_versions']}")
print(f"candidates        : users {report['users_candidate_count']}"
      f" / projects {report['projects_candidate_count']}"
      f" / evidence {report['evidence_candidate_count']}")
print(f"ledger            : {report['audit_ledger_events']}"
      f" events, span {report['ledger_min_max_sequence']}")
print(f"archive table     : {'PRESENT' if report['identity_retirement_archive_present'] else 'absent'}")
print(f"duplicate groups  : username {report['dup_username_groups']}"
      f" email {report['dup_email_groups']}")
print("shape checks      : " + ", ".join(
    f"{k.split('::')[1]}={v}" for k, v in report.items() if k.startswith("shape::")))
print("refs out of set   : " + (", ".join(
    f"{k.split('::')[1]}={v}" for k, v in report.items()
    if k.startswith("fk_out_of_set::")) or "none"))
print(f"tables counted    : {len(counts)} (fingerprints recorded to {OUT})")
print()
if problems:
    print("PREFLIGHT FAILED — do NOT migrate:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("PREFLIGHT PASSED: live state matches the reviewed target set exactly")
