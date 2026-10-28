"""BE-029: prove what the retirement archive actually contains.

Usage: python archive_audit.py <postgres-url> [ids]

Reads identity_retirement_archive and checks every archived row image against
the four synthetic fixture signatures (testuser / test@example.com / testproj /
foo.jpg), then reports the owner/project/evidence linkage. Pass `ids` to also
list the archived user ids and creation timestamps.

This is the "exact rows targeted" evidence: the archive is the pre-deletion
image of every row the migration removed, so anything the migration touched is
visible here and anything it should not have touched would fail the signature
check.
"""
import json
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

URL = sys.argv[1]
SHOW_IDS = len(sys.argv) > 2 and sys.argv[2] == "ids"

report = {}
conn = psycopg2.connect(URL)
conn.set_session(readonly=True, autocommit=True)
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("SELECT current_database() AS db, version() AS v")
    report["database"] = dict(cur.fetchone())["db"]
    cur.execute(
        "SELECT version_num FROM alembic_version")
    report["alembic_version"] = cur.fetchone()["version_num"]
    cur.execute(
        "SELECT source_table, count(*) AS n FROM identity_retirement_archive "
        "GROUP BY source_table ORDER BY source_table")
    report["archive_counts"] = [dict(r) for r in cur.fetchall()]

    cur.execute(
        "SELECT a.row_json->>'id' AS id, a.row_json->>'username' AS username, "
        "a.row_json->>'email' AS email, a.row_json->>'status' AS status, "
        "a.row_json->>'identity_provider' AS identity_provider, "
        "a.row_json->>'external_subject' AS external_subject, "
        "a.row_json->>'created_at' AS created_at, a.retired_at::text AS retired_at "
        "FROM identity_retirement_archive a WHERE a.source_table='users' "
        "ORDER BY a.source_id")
    users = [dict(r) for r in cur.fetchall()]
    report["users_off_signature"] = [
        {"id": u["id"], "username": u["username"], "email": u["email"]}
        for u in users
        if u["username"] != "testuser" or u["email"] != "test@example.com"]
    report["user_columns_present"] = sorted(users[0].keys()) if users else []

    cur.execute(
        "SELECT a.row_json->>'id' AS id, a.row_json->>'name' AS name, "
        "a.row_json->>'owner_id' AS owner_id "
        "FROM identity_retirement_archive a WHERE a.source_table='projects' "
        "ORDER BY a.source_id")
    projects = [dict(r) for r in cur.fetchall()]
    report["projects_off_signature"] = [
        {"id": p["id"], "name": p["name"], "owner_id": p["owner_id"]}
        for p in projects if p["name"] != "testproj"]
    report["projects_owned_by_non_archived_user"] = [
        p["id"] for p in projects
        if p["owner_id"] not in {u["id"] for u in users}]

    cur.execute(
        "SELECT a.row_json->>'id' AS id, a.row_json->>'filename' AS filename, "
        "a.row_json->>'project_id' AS project_id "
        "FROM identity_retirement_archive a WHERE a.source_table='evidence' "
        "ORDER BY a.source_id")
    evidence = [dict(r) for r in cur.fetchall()]
    report["evidence_off_signature"] = [
        {"id": e["id"], "filename": e["filename"], "project_id": e["project_id"]}
        for e in evidence if e["filename"] != "foo.jpg"]
    report["evidence_in_non_archived_project"] = [
        e["id"] for e in evidence
        if e["project_id"] not in {p["id"] for p in projects}]

    report["triple_linkage_ok"] = (
        len(users) == len(projects) == len(evidence)
        and not report["users_off_signature"]
        and not report["projects_off_signature"]
        and not report["evidence_off_signature"]
        and not report["projects_owned_by_non_archived_user"]
        and not report["evidence_in_non_archived_project"])

    # Does any live row still share a username or email with an archived row?
    for col, val in (("username", "testuser"), ("email", "test@example.com")):
        cur.execute(f'SELECT count(*) AS n FROM users WHERE "{col}" = %s', (val,))
        report[f"live_users_with_{col}"] = cur.fetchone()["n"]

    # Ledger rows that mention an archived id (append-only history, must survive).
    ids = [u["id"] for u in users] + [p["id"] for p in projects] + [e["id"] for e in evidence]
    cur.execute(
        "SELECT count(*) AS n FROM audit_ledger_events a "
        "WHERE a.actor_id = ANY(%s::uuid[]) OR a.project_id = ANY(%s::uuid[]) "
        "OR a.resource_id = ANY(%s::uuid[])",
        (ids, ids, ids))
    report["ledger_rows_referencing_archived_ids"] = cur.fetchone()["n"]

    if SHOW_IDS:
        report["archived_users"] = [
            {"id": u["id"], "created_at": str(u["created_at"]),
             "status": u["status"], "identity_provider": u["identity_provider"],
             "external_subject": u["external_subject"]}
            for u in users]

conn.close()
print(json.dumps(report, indent=1, default=str))
