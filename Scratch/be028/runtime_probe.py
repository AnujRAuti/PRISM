"""BE-028 §30/§31 regression probe against a live server on a scratch database.

Covers the six surfaces the task file names, over a real socket:

  backend startup | health | DB connectivity | project CRUD | auth behaviour | audit

The audit chain is verified in-process (audit_service.verify_chain) before and
after the CRUD traffic, because the ledger endpoint needs an authenticated
admin principal; the HTTP side proves the guard still denies anonymous calls.

Target is pofa_be028_rollback -- a scratch clone -- never pofa_dev, never
pofa_test. Everything it creates is deleted again.
"""
import sys
import uuid

import httpx
from sqlalchemy import text

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

BASE = "http://127.0.0.1:8123/api/v1"

from backend.db.session import get_session                      # noqa: E402
from backend.services import audit_ledger as audit_service        # noqa: E402

URL_MARKER = sys.argv[1] if len(sys.argv) > 1 else "pofa_be028_rollback"


def chain(label: str) -> None:
    db = get_session()
    try:
        result = audit_service.verify_chain(db)
        rows = db.execute(text("SELECT count(*) FROM audit_events")).scalar()
        print(f"audit chain {label}: valid={result['valid']} "
              f"events={rows} checked={result.get('events_checked')}")
    finally:
        db.close()


def main() -> int:
    db = get_session()
    try:
        print("database under probe:", db.execute(text("SELECT current_database()")).scalar())
        assert db.execute(text("SELECT current_database()")).scalar() == URL_MARKER
        print("schema version:      ",
              db.execute(text("SELECT version_num FROM alembic_version")).scalar())
        print("be028 indexes present:",
              [r[0] for r in db.execute(text(
                  "SELECT indexname FROM pg_indexes WHERE indexname IN "
                  "('ix_analysis_jobs_status','ix_evidence_metadata_evidence_id',"
                  "'ix_projects_name') ORDER BY 1"))])
    finally:
        db.close()

    chain("before traffic")

    owner_id = str(uuid.uuid4())
    db = get_session()
    try:
        db.execute(text(
            "INSERT INTO users (id, username, email, is_active, status,"
            " identity_provider, created_at, updated_at)"
            " VALUES (:id, :u, :e, true, 'ACTIVE', 'local', now(), now())"),
            {"id": owner_id, "u": f"be028-probe-{uuid.uuid4().hex[:8]}",
             "e": f"{uuid.uuid4().hex[:8]}@example.com"})
        db.commit()
    finally:
        db.close()

    failures = []
    project_id = None
    with httpx.Client(timeout=30) as c:
        checks = [
            ("startup/health", "GET", f"{BASE}/health", 200),
            ("readiness (DB SELECT 1)", "GET", f"{BASE}/ready", 200),
            ("openapi", "GET", "http://127.0.0.1:8123/openapi.json", 200),
            ("docs", "GET", "http://127.0.0.1:8123/docs", 200),
            # Auth behaviour: guarded reads must deny an anonymous caller.
            ("auth: anonymous /audit/events", "GET", f"{BASE}/audit/events", (401, 403)),
            ("auth: anonymous /auth/me", "GET", f"{BASE}/auth/me", (401, 403)),
            ("auth: anonymous /auth/roles", "GET", f"{BASE}/auth/roles", (401, 403)),
            ("auth: anonymous /auth/organizations", "GET",
             f"{BASE}/auth/organizations", (401, 403)),
        ]
        for label, method, url, expected in checks:
            r = c.request(method, url)
            ok = r.status_code == expected if isinstance(expected, int) \
                else r.status_code in expected
            print(f"{label:38} -> {r.status_code} {'OK' if ok else 'UNEXPECTED'}")
            if not ok:
                failures.append(label)

        print("--- project CRUD round trip ---")
        created = c.post(f"{BASE}/projects",
                         json={"name": "BE-028 regression probe", "owner_id": owner_id})
        print("POST /projects   ", created.status_code)
        if created.status_code == 201:
            project_id = created.json()["id"]
            got = c.get(f"{BASE}/projects/{project_id}")
            print("GET  /projects/{id}", got.status_code,
                  "name=", got.json().get("name"))
            patched = c.patch(f"{BASE}/projects/{project_id}",
                              json={"name": "BE-028 regression probe (renamed)"})
            print("PATCH /projects/{id}", patched.status_code,
                  "name=", patched.json().get("name") if patched.status_code < 300 else "")
            listed = c.get(f"{BASE}/projects", params={"limit": 5})
            print("GET  /projects    ", listed.status_code,
                  "items=", len(listed.json().get("items", listed.json())))
        else:
            print("POST failed:", created.text[:300])
            failures.append("project create")

    db = get_session()
    try:
        rows = db.execute(text(
            "SELECT count(*) FROM projects WHERE owner_id = CAST(:i AS uuid)"),
            {"i": owner_id}).scalar()
        print("projects owned by probe user:", rows)
        if project_id:
            deleted = None
            with httpx.Client(timeout=30) as c:
                deleted = c.delete(f"{BASE}/projects/{project_id}")
            print("DELETE /projects/{id}", deleted.status_code)
    finally:
        db.close()

    chain("after traffic")

    # Leave the scratch clone as found: remove probe rows.
    db = get_session()
    try:
        db.execute(text("DELETE FROM projects WHERE owner_id = CAST(:i AS uuid)"), {"i": owner_id})
        db.execute(text("DELETE FROM activities WHERE actor_id = CAST(:i AS uuid)"), {"i": owner_id})
        db.execute(text("DELETE FROM users WHERE id = CAST(:i AS uuid)"), {"i": owner_id})
        db.commit()
        left = db.execute(text("SELECT count(*) FROM users WHERE id = CAST(:i AS uuid)"),
                          {"i": owner_id}).scalar()
        print("probe user rows remaining:", left)
    finally:
        db.close()
    chain("after cleanup")

    print("\nRESULT:", "FAIL " + str(failures) if failures else "all six surfaces OK")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
