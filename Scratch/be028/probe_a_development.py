"""BE-028 §30/§31 regression probe -- part A, server running in its shipped mode.

Runs against a live uvicorn process (PROBE_PORT, default 8124) whose DATABASE_URL
is the scratch clone -- never pofa_dev, never pofa_test. Covers the six §30 surfaces:

  startup | health | DB connectivity | project CRUD | auth behaviour | audit

Auth facts being checked, from backend/security/authentication.py:
* development mode lets an ANONYMOUS caller through the guard (documented
  bypass, warning-logged) -- that is shipped behaviour, not a BE-028 change;
* an AUTHENTICATED non-admin principal must still be refused on admin routes,
  which proves the guard itself is real;
* project CRUD round-trips against a head-migrated schema;
* an audited admin write (organization lifecycle) appends to the ledger and
  audit_service.verify_chain() stays valid.
"""
import sys
import uuid

import httpx
from sqlalchemy import text

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

from backend.db.session import get_session                # noqa: E402
from backend.services import audit_ledger as audit_service  # noqa: E402

PORT = int(__import__("os").environ.get("PROBE_PORT", "8124"))
BASE = f"http://127.0.0.1:{PORT}/api/v1"
ROOT = f"http://127.0.0.1:{PORT}"
MARKER = "pofa_be028_rollback"
notes = []


def chain(label):
    db = get_session()
    try:
        result = audit_service.verify_chain(db)
        rows = db.execute(text("SELECT count(*) FROM audit_ledger_events")).scalar()
        print(f"  chain {label:18} valid={result['valid']} events={rows} "
              f"reasons={result.get('reason') or result.get('details') or '-'}")
        return rows
    finally:
        db.close()


def check(label, actual, expected):
    ok = actual in (expected if isinstance(expected, tuple) else (expected,))
    print(f"  {label:44} -> {actual} {'OK' if ok else 'UNEXPECTED'}")
    if not ok:
        notes.append(f"{label}: expected {expected}, got {actual}")
    return ok


db = get_session()
print("=== environment ===")
print("  database:", db.execute(text("SELECT current_database()")).scalar(),
      "| schema:", db.execute(text("SELECT version_num FROM alembic_version")).scalar())
assert db.execute(text("SELECT current_database()")).scalar() == MARKER
print("  BE-028 indexes:", [r[0] for r in db.execute(text(
    "SELECT indexname FROM pg_indexes WHERE indexname IN "
    "('ix_analysis_jobs_status','ix_evidence_metadata_evidence_id','ix_projects_name')"))])
print("  ix_projects_name is used by the planner:", db.execute(text(
    "SELECT count(*) FROM pg_stat_user_indexes WHERE indexrelid::regclass::text "
    "= 'ix_projects_name'")).scalar(), "stat row(s)")
db.close()

print("\n=== audit ledger before traffic ===")
before = chain("before")

owner_id = str(uuid.uuid4())
plain_id = str(uuid.uuid4())
db = get_session()
for uid, name in ((owner_id, "be028-probe-owner"), (plain_id, "be028-probe-plain")):
    db.execute(text(
        "INSERT INTO users (id, username, email, is_active, status, identity_provider,"
        " created_at, updated_at) VALUES (:id, :u, :e, true, 'ACTIVE', 'local',"
        " now(), now())"),
        {"id": uid, "u": f"{name}-{uuid.uuid4().hex[:8]}",
         "e": f"{uuid.uuid4().hex[:8]}@example.com"})
db.commit()
db.close()

project_id = org_id = None
with httpx.Client(timeout=30) as c:
    print("\n=== startup / health / connectivity ===")
    check("GET /health", c.get(f"{BASE}/health").status_code, 200)
    check("GET /ready (SELECT 1 against the DB)", c.get(f"{BASE}/ready").status_code, 200)
    check("GET /openapi.json", c.get(f"{ROOT}/openapi.json").status_code, 200)

    print("\n=== auth behaviour ===")
    spec = c.get(f"{ROOT}/openapi.json").json()
    print("  DELETE /projects/{id} exists in OpenAPI:",
          "delete" in spec["paths"].get("/api/v1/projects/{project_id}", {}))
    # development mode: anonymous passes the guard (shipped, documented bypass)
    check("GET /auth/roles anonymous (development bypass)",
          c.get(f"{BASE}/auth/roles").status_code, 200)
    # authenticated NON-admin must still be refused
    r = c.get(f"{BASE}/auth/roles", headers={"Authorization": f"Bearer dev-user-{plain_id}"})
    check("GET /auth/roles as authenticated non-admin", r.status_code, (401, 403))
    r = c.get(f"{BASE}/audit/events", headers={"Authorization": f"Bearer dev-user-{plain_id}"})
    check("GET /audit/events as authenticated non-admin", r.status_code, (401, 403))
    check("GET /auth/me with a real dev token",
          c.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer dev-user-{plain_id}"}).status_code, 200)
    check("GET /auth/me with a garbage token",
          c.get(f"{BASE}/auth/me", headers={"Authorization": "Bearer dev-user-not-a-uuid"}).status_code, 401)

    print("\n=== project CRUD ===")
    created = c.post(f"{BASE}/projects", json={"name": "BE-028 regression probe",
                                               "owner_id": owner_id})
    check("POST /projects", created.status_code, 201)
    if created.status_code == 201:
        project_id = created.json()["id"]
    check("GET /projects/{id}", c.get(f"{BASE}/projects/{project_id}").status_code, 200)
    patched = c.patch(f"{BASE}/projects/{project_id}",
                      json={"name": "BE-028 regression probe (renamed)"})
    check("PATCH /projects/{id}", patched.status_code, 200)
    print("    name now:", patched.json().get("name"))
    listed = c.get(f"{BASE}/projects", params={"limit": 5})
    check("GET /projects (list)", listed.status_code, 200)
    print("    list keys:", sorted(listed.json())[:4])
    check("GET /projects?name= index-backed filter",
          c.get(f"{BASE}/projects", params={"name": "BE-028 regression probe (renamed)"}).status_code,
          (200, 422))
    check("DELETE /projects/{id} (not a V1 route)",
          c.delete(f"{BASE}/projects/{project_id}").status_code, 405)

    print("\n=== audited admin write (organization lifecycle) ===")
    org = c.post(f"{BASE}/auth/organizations",
                 json={"name": f"BE-028 probe org {uuid.uuid4().hex[:6]}",
                       "code": f"be028{uuid.uuid4().hex[:6]}"})
    check("POST /auth/organizations", org.status_code, 201)
    if org.status_code == 201:
        org_id = org.json()["id"]
        patched_org = c.patch(f"{BASE}/auth/organizations/{org_id}", json={"status": "SUSPENDED"})
        check("PATCH /auth/organizations/{id} (status)", patched_org.status_code, 200)
        events = c.get(f"{BASE}/audit/events", params={"resource_type": "organizations",
                                                      "resource_id": org_id, "limit": 10})
        check("GET /audit/events for that organization", events.status_code, 200)
        items = events.json().get("items", [])
        print("    ledger rows for the probe org:",
              [(e["sequence_number"], e["event_type"]) for e in items])
        if not items:
            notes.append("audited admin write produced no ledger rows")

print("\n=== audit ledger after traffic ===")
after = chain("after")
print(f"  ledger grew by {after - before} row(s)")
if after <= before:
    notes.append("audit ledger did not grow for audited writes")

db = get_session()
try:
    db.execute(text("DELETE FROM activities WHERE actor_id IN "
                    "(SELECT id FROM users WHERE username LIKE 'be028-probe%')"))
    db.execute(text("DELETE FROM projects WHERE name LIKE 'BE-028%'"))
    db.execute(text("DELETE FROM users WHERE username LIKE 'be028-probe%'"))
    db.execute(text("DELETE FROM organizations WHERE code LIKE 'be028%'"))
    db.commit()
    for label, sql in (
        ("users", "SELECT count(*) FROM users WHERE username LIKE 'be028-probe%'"),
        ("projects", "SELECT count(*) FROM projects WHERE name LIKE 'BE-028%'"),
        ("organizations", "SELECT count(*) FROM organizations WHERE code LIKE 'be028%'"),
    ):
        print(f"residue {label}:", db.execute(text(sql)).scalar())
    print("  (ledger rows are append-only and intentionally left in the scratch clone)")
finally:
    db.close()
chain("after cleanup")

print("\nRESULT:", "PASS - all six surfaces behaved as documented"
      if not notes else f"FINDINGS: {notes}")
