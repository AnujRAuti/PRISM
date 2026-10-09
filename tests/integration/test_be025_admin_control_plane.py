"""BE-025 integration tests: administrative control plane.

Covers the containment rules (E1/E2/E4), last-GLOBAL-administrator protection,
organization/unit/user lifecycle, project scope/ownership administration,
audit events, pagination/enumeration safety, API-client scope enforcement, the
M1 database constraint, and idempotency under duplicates. Runs against the
isolated TEST_DATABASE_URL with real HTTP via TestClient (BE-023 bootstrap).
"""

import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    AuditLedgerEvent,
    Organization,
    OrganizationalUnit,
    Project,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_session
from backend.services import authorization as auth_service


client = TestClient(app)


def headers_for(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def make_user(username: str) -> User:
    session = get_session()
    try:
        user = User(username=f"{username}-{uuid4().hex[:8]}",
                    email=f"{uuid4().hex[:8]}@example.com")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()


def assign(user_id: str, role: str, scope: str, scope_id: str | None = None):
    """Internal (actor=None) assignment, as BE-016 tests do."""
    session = get_session()
    try:
        kwargs: dict = {}
        if scope == "ORGANIZATION":
            kwargs["organization_id"] = scope_id
        elif scope == "ORGANIZATIONAL_UNIT":
            kwargs["organizational_unit_id"] = scope_id
        elif scope == "PROJECT":
            kwargs["project_id"] = scope_id
        row, _ = auth_service.assign_role(
            session, user_id=user_id, role_name=role, scope_type=scope, **kwargs)
        session.commit()
        session.refresh(row)
        return {"id": str(row.id)}
    finally:
        session.close()


def create_org(code: str) -> Organization:
    session = get_session()
    try:
        org = auth_service.create_organization(
            session, name=f"Org {code}", code=f"org-{code}-{uuid4().hex[:6]}")
        session.commit()
        session.refresh(org)
        session.expunge(org)
        return org
    finally:
        session.close()


def walk_organizations(headers: dict, limit: int = 25) -> list[dict]:
    """Every organization the caller can see, one page at a time.

    ``total`` is the caller-visible count, not the page length, so a test that
    asks "is X listed?" has to walk the listing. Asserting membership of the
    first page instead makes the test depend on the database being no larger
    than the default 50-row page -- and every suite run creates more
    organizations, so that assumption has a shelf life.
    """
    items: list[dict] = []
    offset = 0
    while True:
        response = client.get(
            f"/api/v1/auth/organizations?limit={limit}&offset={offset}",
            headers=headers)
        assert response.status_code == 200
        page = response.json()
        items.extend(page["items"])
        if len(items) >= page["total"]:
            return items
        if not page["items"]:
            raise AssertionError(
                f"pagination stalled: {len(items)} of {page['total']} at offset {offset}")
        offset += limit


def create_unit(org_id: str, code: str) -> OrganizationalUnit:
    session = get_session()
    try:
        unit = auth_service.create_organizational_unit(
            session, organization_id=org_id, name=f"Unit {code}", code=code)
        session.commit()
        session.refresh(unit)
        session.expunge(unit)
        return unit
    finally:
        session.close()


def make_project(owner_id: str, name: str) -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": owner_id})
    assert response.status_code == 201
    return response.json()


def bind_project(project_id: str, *, org_id: str | None = None,
                 unit_id: str | None = None) -> None:
    session = get_session()
    try:
        session.execute(
            text("UPDATE projects SET organization_id=:o, organizational_unit_id=:u "
                 "WHERE id=:i"),
            {"o": org_id, "u": unit_id, "i": project_id},
        )
        session.commit()
    finally:
        session.close()


def cleanup(*, user_ids=(), project_ids=(), org_ids=(), unit_ids=()) -> None:
    session = get_session()
    try:
        # Assignments reference users AND projects; projects reference
        # users (owner_id). Delete in FK-safe order.
        if user_ids or project_ids:
            if user_ids:
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.user_id.in_(user_ids)).delete(
                    synchronize_session=False)
            if project_ids:
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.project_id.in_(project_ids)).delete(
                    synchronize_session=False)
        if project_ids:
            session.query(Project).filter(Project.id.in_(project_ids)).delete(
                synchronize_session=False)
        if user_ids:
            session.query(User).filter(User.id.in_(user_ids)).delete(
                synchronize_session=False)
        if unit_ids:
            session.query(OrganizationalUnit).filter(
                OrganizationalUnit.id.in_(unit_ids)).delete(synchronize_session=False)
        if org_ids:
            session.query(Organization).filter(Organization.id.in_(org_ids)).delete(
                synchronize_session=False)
        session.commit()
    finally:
        session.close()


def global_admin() -> User:
    admin = make_user("be025-admin")
    assign(str(admin.id), "ADMINISTRATOR", "GLOBAL", None)
    return admin


def audit_events(event_type: str, resource_id: str | None = None):
    session = get_session()
    try:
        query = session.query(AuditLedgerEvent).filter(
            AuditLedgerEvent.event_type == event_type)
        if resource_id:
            query = query.filter(AuditLedgerEvent.resource_id == resource_id)
        rows = query.order_by(AuditLedgerEvent.sequence_number).all()
        return [dict(id=str(r.id), payload=r.payload, actor_id=str(r.actor_id)
                     if r.actor_id else None) for r in rows]
    finally:
        session.close()


@pytest.fixture(autouse=True)
def seed_catalogue():
    session = get_session()
    try:
        auth_service.ensure_default_catalogue(session)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Authorization matrix
# ---------------------------------------------------------------------------

def test_administrator_can_manage_org_within_scope():
    admin = global_admin()
    org = create_org("scope")
    outsider_org = create_org("other")
    org_admin = make_user("be025-orgadmin")
    assign(str(org_admin.id), "ADMINISTRATOR", "ORGANIZATION", str(org.id))
    try:
        headers = headers_for(str(org_admin.id))
        patched = client.patch(f"/api/v1/auth/organizations/{org.id}",
                               json={"name": "Renamed"}, headers=headers)
        assert patched.status_code == 200
        assert patched.json()["name"] == "Renamed"
        assert patched.json()["code"] == org.code  # code immutable
        # Reading one's own organization uses exactly the update guard (DF-D-02).
        mine = client.get(f"/api/v1/auth/organizations/{org.id}", headers=headers)
        assert mine.status_code == 200
        assert mine.json()["id"] == str(org.id)
        # Foreign organization is indistinguishable from absent (404).
        foreign = client.patch(f"/api/v1/auth/organizations/{outsider_org.id}",
                               json={"name": "Stolen"}, headers=headers)
        assert foreign.status_code == 404
        foreign_read = client.get(f"/api/v1/auth/organizations/{outsider_org.id}",
                                  headers=headers)
        assert foreign_read.status_code == 404
        assert client.get(f"/api/v1/auth/organizations/{uuid4()}",
                          headers=headers).status_code == 404
    finally:
        cleanup(user_ids=[str(admin.id), str(org_admin.id)],
                org_ids=[str(org.id), str(outsider_org.id)])


def test_non_admin_roles_denied_admin_plane():
    admin = global_admin()
    org = create_org("denials")
    plain_users = {}
    try:
        for role in ("REVIEWER", "FIELD_OFFICER", "CITIZEN", "SUPERVISOR"):
            user = make_user(f"be025-{role.lower()}")
            assign(str(user.id), role, "GLOBAL", None)
            plain_users[role] = user
            headers = headers_for(str(user.id))
            assert client.get("/api/v1/auth/organizations",
                              headers=headers).status_code == 403
            assert client.patch(f"/api/v1/auth/organizations/{org.id}",
                                json={"name": "nope"},
                                headers=headers).status_code == 403
            assert client.post(f"/api/v1/auth/users/{user.id}/roles",
                               json={"role_name": "REVIEWER",
                                     "scope_type": "GLOBAL"},
                               headers=headers).status_code == 403
        # Anonymous callers are rejected only in enforcing mode; development
        # mode keeps its explicit bypass contract.
        original_mode = settings.auth_mode
        settings.auth_mode = "enforcing"
        try:
            assert client.get("/api/v1/auth/organizations").status_code == 401
            assert client.get("/api/v1/auth/users").status_code == 401
        finally:
            settings.auth_mode = original_mode
    finally:
        cleanup(user_ids=[str(admin.id)] + [str(u.id) for u in plain_users.values()],
                org_ids=[str(org.id)])


def test_unit_boundaries_enforced():
    admin = global_admin()
    org_a = create_org("unitA")
    org_b = create_org("unitB")
    unit_b = create_unit(str(org_b.id), f"b-{uuid4().hex[:6]}")
    admin_headers = headers_for(str(admin.id))
    created = client.post(f"/api/v1/auth/organizations/{org_a.id}/units",
                          json={"name": "Unit A1", "code": f"a1-{uuid4().hex[:6]}"},
                          headers=admin_headers)
    assert created.status_code == 201
    unit_a_id = created.json()["id"]
    org_a_admin = make_user("be025-orga-admin")
    assign(str(org_a_admin.id), "ADMINISTRATOR", "ORGANIZATION", str(org_a.id))
    try:
        headers = headers_for(str(org_a_admin.id))
        assert client.get(f"/api/v1/auth/units/{unit_a_id}",
                          headers=headers).status_code == 200
        # A unit of another organization is indistinguishable from absent.
        assert client.get(f"/api/v1/auth/units/{unit_b.id}",
                          headers=headers).status_code == 404
        assert client.patch(f"/api/v1/auth/units/{unit_b.id}",
                            json={"name": "hijack"},
                            headers=headers).status_code == 404
        # Wrong parent organization: deterministic 404 on create.
        assert client.post(
            f"/api/v1/auth/organizations/{uuid4()}/units",
            json={"name": "ghost", "code": "ghost"},
            headers=headers).status_code == 404
        patched = client.patch(f"/api/v1/auth/units/{unit_a_id}",
                               json={"status": "SUSPENDED"}, headers=headers)
        assert patched.status_code == 200
        assert patched.json()["status"] == "SUSPENDED"
    finally:
        cleanup(user_ids=[str(admin.id), str(org_a_admin.id)],
                org_ids=[str(org_a.id), str(org_b.id)], unit_ids=[unit_b.id, unit_a_id])


# ---------------------------------------------------------------------------
# Role assignment / revocation
# ---------------------------------------------------------------------------

def test_scoped_assignment_lifecycle_via_api():
    admin = global_admin()
    org = create_org("lifecycle")
    target = make_user("be025-target")
    admin_headers = headers_for(str(admin.id))
    try:
        created = client.post(
            f"/api/v1/auth/users/{target.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "ORGANIZATION",
                  "organization_id": str(org.id)}, headers=admin_headers)
        assert created.status_code == 201
        assignment_id = created.json()["id"]
        assert created.json()["role_name"] == "REVIEWER"
        listed = client.get(f"/api/v1/auth/users/{target.id}/roles",
                            headers=admin_headers)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [assignment_id]
        revoked = client.delete(
            f"/api/v1/auth/users/{target.id}/roles/{assignment_id}",
            headers=admin_headers)
        assert revoked.status_code == 204
        # Revoked assignment stops authorizing immediately.
        after = client.get(f"/api/v1/auth/users/{target.id}/roles",
                           headers=admin_headers)
        assert after.json()["items"] == []
        assert audit_events("ROLE_ASSIGNED", assignment_id)
        assert audit_events("ROLE_REVOKED", assignment_id)
    finally:
        cleanup(user_ids=[str(admin.id), str(target.id)], org_ids=[str(org.id)])


def test_role_assignment_list_reports_the_visible_total_not_the_page_length():
    """``total`` counts every visible assignment, not the rows on this page.

    ``list_user_roles`` sliced the list and then reported ``total=len(rows)``,
    so the total shrank to whatever ``limit`` was asked for and a client walking
    pages could never tell whether assignments were still waiting.
    """
    admin = global_admin()
    org_a, org_b = create_org("totalA"), create_org("totalB")
    target = make_user("be025-total")
    admin_headers = headers_for(str(admin.id))
    try:
        for org in (org_a, org_b):
            created = client.post(
                f"/api/v1/auth/users/{target.id}/roles",
                json={"role_name": "REVIEWER", "scope_type": "ORGANIZATION",
                      "organization_id": str(org.id)}, headers=admin_headers)
            assert created.status_code == 201
        page = client.get(f"/api/v1/auth/users/{target.id}/roles?limit=1&offset=0",
                          headers=admin_headers).json()
        assert len(page["items"]) == 1
        assert page["total"] == 2, page
        collected = []
        for offset in range(page["total"]):
            body = client.get(
                f"/api/v1/auth/users/{target.id}/roles?limit=1&offset={offset}",
                headers=admin_headers).json()
            assert body["total"] == 2, body
            collected += [item["id"] for item in body["items"]]
        assert len(collected) == len(set(collected)) == 2, collected
    finally:
        cleanup(user_ids=[str(admin.id), str(target.id)],
                org_ids=[str(org_a.id), str(org_b.id)])


def test_duplicate_assignment_is_idempotent_and_concurrent_safe():
    admin = global_admin()
    org = create_org("dup")
    target = make_user("be025-dup")
    headers = headers_for(str(admin.id))
    body = {"role_name": "REVIEWER", "scope_type": "ORGANIZATION",
            "organization_id": str(org.id)}
    try:
        codes = []
        threads = []

        def fire():
            codes.append(client.post(
                f"/api/v1/auth/users/{target.id}/roles", json=body,
                headers=headers).status_code)

        for _ in range(8):
            thread = threading.Thread(target=fire)
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        assert len(codes) == 8
        assert all(code in (200, 201) for code in codes)
        session = get_session()
        try:
            count = session.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id == str(target.id)).count()
            assert count == 1
        finally:
            session.close()
    finally:
        cleanup(user_ids=[str(admin.id), str(target.id)], org_ids=[str(org.id)])


def test_privilege_escalation_attempts_denied():
    admin = global_admin()
    org_a = create_org("escA")
    org_b = create_org("escB")
    victim = make_user("be025-victim")
    org_admin = make_user("be025-esc-admin")
    assign(str(org_admin.id), "ADMINISTRATOR", "ORGANIZATION", str(org_a.id))
    headers = headers_for(str(org_admin.id))
    try:
        # E1: organization admin cannot mint GLOBAL assignments (403: this is
        # about the actor's own capability, not a resource).
        assert client.post(
            f"/api/v1/auth/users/{victim.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "GLOBAL"},
            headers=headers).status_code == 403
        # E2: cross-organization assignment is invisible (404).
        assert client.post(
            f"/api/v1/auth/users/{victim.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "ORGANIZATION",
                  "organization_id": str(org_b.id)},
            headers=headers).status_code == 404
        # No ADMINISTRATOR delegation from non-GLOBAL authority (403).
        assert client.post(
            f"/api/v1/auth/users/{victim.id}/roles",
            json={"role_name": "ADMINISTRATOR", "scope_type": "ORGANIZATION",
                  "organization_id": str(org_a.id)},
            headers=headers).status_code == 403
        # In-scope delegation of a non-admin role works.
        assert client.post(
            f"/api/v1/auth/users/{victim.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "ORGANIZATION",
                  "organization_id": str(org_a.id)},
            headers=headers).status_code == 201
        # The org admin cannot revoke assignments outside their scope: a
        # GLOBAL assignment made by the super admin is 403 territory.
        global_role = assign(str(victim.id), "REVIEWER", "GLOBAL", None)
        assert client.delete(
            f"/api/v1/auth/users/{victim.id}/roles/{global_role['id']}",
            headers=headers).status_code == 403
        # GLOBAL admin may revoke it again.
        assert client.delete(
            f"/api/v1/auth/users/{victim.id}/roles/{global_role['id']}",
            headers=headers_for(str(admin.id))).status_code == 204
        session = get_session()
        try:
            # The victim holds exactly the one in-scope REVIEWER grant.
            assert session.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id == str(victim.id)).count() == 1
        finally:
            session.close()
    finally:
        cleanup(user_ids=[str(admin.id), str(victim.id), str(org_admin.id)],
                org_ids=[str(org_a.id), str(org_b.id)])


def test_last_global_administrator_guard():
    # Determinism: park every other GLOBAL administrator assignment for the
    # duration of the test, then restore it verbatim. The guard counts distinct
    # active GLOBAL administrators, so the test must own that population --
    # without the restore it would permanently damage the shared test
    # database's administrator baseline for every later run.
    session = get_session()
    try:
        parked = [dict(row) for row in session.execute(text(
            "SELECT id, user_id, role_id, scope_type, organization_id, "
            "organizational_unit_id, project_id, created_at "
            "FROM user_role_assignments WHERE scope_type = 'GLOBAL'"
        )).mappings().all()]
        for row in parked:
            session.query(UserRoleAssignment).filter(
                UserRoleAssignment.id == row["id"]).delete(
                synchronize_session=False)
        session.commit()
    finally:
        session.close()
    admin_one = make_user("be025-last1")
    admin_two = make_user("be025-last2")
    row_one = assign(str(admin_one.id), "ADMINISTRATOR", "GLOBAL", None)
    row_two = assign(str(admin_two.id), "ADMINISTRATOR", "GLOBAL", None)
    headers_two = headers_for(str(admin_two.id))
    try:
        # Two admins: revoking one succeeds.
        assert client.delete(
            f"/api/v1/auth/users/{admin_one.id}/roles/{row_one['id']}",
            headers=headers_two).status_code == 204
        # One admin left (admin_two): self-revocation is refused.
        refused = client.delete(
            f"/api/v1/auth/users/{admin_two.id}/roles/{row_two['id']}",
            headers=headers_two)
        assert refused.status_code == 409
        # Deactivating the last admin is refused as well.
        assert client.patch(f"/api/v1/auth/users/{admin_two.id}/status",
                            json={"status": "DISABLED"},
                            headers=headers_two).status_code == 409
        # Suspension of an ordinary user by the last admin still works.
        bystander = make_user("be025-bystander")
        try:
            suspended = client.patch(
                f"/api/v1/auth/users/{bystander.id}/status",
                json={"status": "SUSPENDED"}, headers=headers_two)
            assert suspended.status_code == 200
            assert suspended.json()["status"] == "SUSPENDED"
            assert audit_events("USER_STATUS_CHANGED", str(bystander.id))
        finally:
            cleanup(user_ids=[str(bystander.id)])
        assert 409 == client.delete(
            f"/api/v1/auth/users/{admin_two.id}/roles/{row_two['id']}",
            headers=headers_two).status_code
    finally:
        # Restore previously parked GLOBAL assignments for the rest of the run.
        cleanup(user_ids=[str(admin_one.id), str(admin_two.id)])
        session = get_session()
        try:
            for row in parked:
                session.execute(text(
                    "INSERT INTO user_role_assignments (id, user_id, role_id, "
                    "scope_type, organization_id, organizational_unit_id, "
                    "project_id, created_at) VALUES (:id, :user_id, :role_id, "
                    ":scope_type, :organization_id, :organizational_unit_id, "
                    ":project_id, :created_at) ON CONFLICT (id) DO NOTHING"), row)
            session.commit()
        finally:
            session.close()

    session = get_session()
    try:
        remaining = session.query(UserRoleAssignment).filter(
            UserRoleAssignment.scope_type == "GLOBAL").count()
    finally:
        session.close()
    assert remaining == len(parked), (
        f"GLOBAL administrator baseline must be restored exactly: "
        f"parked {len(parked)}, now {remaining}")


# ---------------------------------------------------------------------------
# Organization lifecycle + audit
# ---------------------------------------------------------------------------

def test_organization_lifecycle_noop_audit_and_isolation():
    admin = global_admin()
    org = create_org("life")
    project = make_project(str(admin.id), "life proj")
    bind_project(project["id"], org_id=str(org.id))
    org_user = make_user("be025-orguser")
    assign(str(org_user.id), "REVIEWER", "ORGANIZATION", str(org.id))
    admin_headers = headers_for(str(admin.id))
    try:
        assert client.get(f"/api/v1/projects/{project['id']}",
                          headers=headers_for(str(org_user.id))).status_code == 200
        before = len(audit_events("ORGANIZATION_UPDATED", str(org.id)))
        patched = client.patch(
            f"/api/v1/auth/organizations/{org.id}",
            json={"name": "Renamed life", "status": "SUSPENDED"},
            headers=admin_headers)
        assert patched.status_code == 200
        events = audit_events("ORGANIZATION_UPDATED", str(org.id))
        assert len(events) == before + 1
        assert events[-1]["payload"]["before"]["status"] == "ACTIVE"
        assert events[-1]["payload"]["after"]["status"] == "SUSPENDED"
        assert events[-1]["actor_id"] == str(admin.id)
        # Suspended organization: scoped grants go inert immediately.
        assert client.get(f"/api/v1/projects/{project['id']}",
                          headers=headers_for(str(org_user.id))).status_code in (403, 404)
        # No-op repeat PATCH performs no second audit event.
        noop = client.patch(
            f"/api/v1/auth/organizations/{org.id}",
            json={"name": "Renamed life", "status": "SUSPENDED"},
            headers=admin_headers)
        assert noop.status_code == 200
        assert len(audit_events("ORGANIZATION_UPDATED", str(org.id))) == before + 1
        # Reactivation restores access.
        restored = client.patch(f"/api/v1/auth/organizations/{org.id}",
                                json={"status": "ACTIVE"}, headers=admin_headers)
        assert restored.json()["status"] == "ACTIVE"
        assert client.get(f"/api/v1/projects/{project['id']}",
                          headers=headers_for(str(org_user.id))).status_code == 200
        # Cross-org inference is blocked on the list endpoint too. The endpoint
        # is paginated (default page 50) and this organization is now named
        # "Renamed life", which sorts near the end of 94 rows, so "is it listed"
        # has to be answered by the whole listing rather than page one.
        listed = client.get("/api/v1/auth/organizations", headers=admin_headers)
        assert listed.status_code == 200
        enumerated = walk_organizations(admin_headers)
        assert listed.json()["total"] == len(enumerated), (
            "total must count every visible organization, not the returned page")
        ids = [item["id"] for item in enumerated]
        assert ids.count(str(org.id)) == 1
        scoped_list = client.get(
            "/api/v1/auth/organizations",
            headers=headers_for(str(org_user.id)))
        assert scoped_list.status_code == 403  # REVIEWER has no org.manage
    finally:
        cleanup(user_ids=[str(admin.id), str(org_user.id)],
                project_ids=[project["id"]], org_ids=[str(org.id)])


# ---------------------------------------------------------------------------
# Project administration (E4 movement + audit)
# ---------------------------------------------------------------------------

def test_project_scope_administration():
    admin = global_admin()
    org_a = create_org("moveA")
    org_b = create_org("moveB")
    unit_b = create_unit(str(org_b.id), f"ub-{uuid4().hex[:6]}")
    project = make_project(str(admin.id), "scope proj")
    org_a_admin = make_user("be025-move-admin")
    assign(str(org_a_admin.id), "ADMINISTRATOR", "ORGANIZATION", str(org_a.id))
    admin_headers = headers_for(str(admin.id))
    a_headers = headers_for(str(org_a_admin.id))
    try:
        # Unscoped projects are invisible to organization admins (404), so a
        # GLOBAL actor performs the initial bind.
        assert client.patch(f"/api/v1/auth/projects/{project['id']}/scope",
                            json={"organization_id": str(org_a.id)},
                            headers=a_headers).status_code == 404
        bound = client.patch(f"/api/v1/auth/projects/{project['id']}/scope",
                             json={"organization_id": str(org_a.id)},
                             headers=admin_headers)
        assert bound.status_code == 200
        assert bound.json()["organization_id"] == str(org_a.id)
        assert audit_events("PROJECT_SCOPE_CHANGED", project["id"])
        # Within-scope ADMINISTRATIVE work is allowed for the organization
        # admin, but ADMINISTRATOR holds no project.read: administrative
        # authority never implies substantive project read (fail-closed 403).
        in_scope = client.get(f"/api/v1/projects/{project['id']}", headers=a_headers)
        assert in_scope.status_code == 403
        # While the project is still inside org_a, the org admin has current-
        # scope authority, so the clear-refusal is the service 403 (clearing a
        # binding requires GLOBAL), NOT a 404.
        assert client.patch(
            f"/api/v1/auth/projects/{project['id']}/scope",
            json={"organization_id": None},
            headers=a_headers).status_code == 403
        # Cross-org escape attempts are denied (404 on foreign destination).
        assert client.patch(
            f"/api/v1/auth/projects/{project['id']}/scope",
            json={"organization_id": str(org_b.id)},
            headers=a_headers).status_code == 404
        assert client.patch(
            f"/api/v1/auth/projects/{project['id']}/scope",
            json={"organization_id": str(org_b.id),
                  "organizational_unit_id": str(unit_b.id)},
            headers=a_headers).status_code == 404
        # GLOBAL can move across organizations (documented capability).
        moved = client.patch(
            f"/api/v1/auth/projects/{project['id']}/scope",
            json={"organization_id": str(org_b.id),
                  "organizational_unit_id": str(unit_b.id)},
            headers=admin_headers)
        assert moved.status_code == 200
        assert moved.json()["organizational_unit_id"] == str(unit_b.id)
        # Unit/organization mismatch is a deterministic 422.
        assert client.patch(
            f"/api/v1/auth/projects/{project['id']}/scope",
            json={"organization_id": str(org_a.id),
                  "organizational_unit_id": str(unit_b.id)},
            headers=admin_headers).status_code == 422
        # GLOBAL clears the whole binding (200, both null).
        cleared = client.patch(
            f"/api/v1/auth/projects/{project['id']}/scope",
            json={"organization_id": None, "organizational_unit_id": None},
            headers=admin_headers)
        assert cleared.status_code == 200
        assert cleared.json()["organization_id"] is None
    finally:
        cleanup(user_ids=[str(admin.id), str(org_a_admin.id)],
                project_ids=[project["id"]],
                org_ids=[str(org_a.id), str(org_b.id)], unit_ids=[unit_b.id])


def test_project_ownership_transfer():
    admin = global_admin()
    project = make_project(str(admin.id), "own proj")
    new_owner = make_user("be025-newowner")
    disabled = make_user("be025-disabled")
    session = get_session()
    try:
        row = session.query(User).filter(User.id == str(disabled.id)).one()
        row.status = "DISABLED"
        session.commit()
    finally:
        session.close()
    headers = headers_for(str(admin.id))
    try:
        refused = client.post(
            f"/api/v1/auth/projects/{project['id']}/ownership",
            json={"owner_id": str(disabled.id)}, headers=headers)
        assert refused.status_code == 422
        moved = client.post(
            f"/api/v1/auth/projects/{project['id']}/ownership",
            json={"owner_id": str(new_owner.id)}, headers=headers)
        assert moved.status_code == 200
        assert moved.json()["owner_id"] == str(new_owner.id)
        events = audit_events("PROJECT_OWNERSHIP_CHANGED", project["id"])
        assert events and events[-1]["payload"]["owner_id"]["after"] == str(new_owner.id)
        assert 404 == client.post(
            f"/api/v1/auth/projects/{uuid4()}/ownership",
            json={"owner_id": str(new_owner.id)}, headers=headers).status_code
    finally:
        cleanup(user_ids=[str(admin.id), str(new_owner.id), str(disabled.id)],
                project_ids=[project["id"]])


# ---------------------------------------------------------------------------
# API clients, pagination, validation, DB constraint, chain
# ---------------------------------------------------------------------------

def test_api_client_scope_enforcement():
    admin = global_admin()
    org = create_org("client")
    project = make_project(str(admin.id), "client proj")
    bind_project(project["id"], org_id=str(org.id))
    target = make_user("be025-client-target")
    headers = headers_for(str(admin.id))
    client_ids = []
    try:
        weak = client.post("/api/v1/auth/clients",
                           json={"name": f"weak-{uuid4().hex[:8]}",
                                 "scopes": ["evidence.read"]}, headers=headers)
        assert weak.status_code == 201
        weak_id = weak.json()["id"]
        client_ids.append(weak_id)
        weak_headers = {"Authorization": f"Bearer dev-client-{weak_id}"}
        assert client.post(
            f"/api/v1/auth/users/{target.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "ORGANIZATION",
                  "organization_id": str(org.id)},
            headers=weak_headers).status_code == 403
        strong = client.post("/api/v1/auth/clients",
                             json={"name": f"strong-{uuid4().hex[:8]}",
                                   "scopes": ["role.manage"],
                                   "project_id": project["id"]}, headers=headers)
        assert strong.status_code == 201
        strong_id = strong.json()["id"]
        client_ids.append(strong_id)
        strong_headers = {"Authorization": f"Bearer dev-client-{strong_id}"}
        # PROJECT-bound client: within-bound assignment allowed...
        assert client.post(
            f"/api/v1/auth/users/{target.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "PROJECT",
                  "project_id": project["id"]},
            headers=strong_headers).status_code == 201
        # ...GLOBAL and any broader target denied (403/404).
        assert client.post(
            f"/api/v1/auth/users/{target.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "GLOBAL"},
            headers=strong_headers).status_code == 403
        assert client.post(
            f"/api/v1/auth/users/{target.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "ORGANIZATION",
                  "organization_id": str(org.id)},
            headers=strong_headers).status_code == 404
    finally:
        session = get_session()
        try:
            from backend.db.models import ApiClient

            session.query(ApiClient).filter(
                ApiClient.id.in_(client_ids)).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()
        cleanup(user_ids=[str(admin.id), str(target.id)],
                project_ids=[project["id"]], org_ids=[str(org.id)])


def test_pagination_bounds_and_enumeration():
    admin = global_admin()
    orgs = [create_org(f"page{i}") for i in range(3)]
    headers = headers_for(str(admin.id))
    try:
        assert client.get("/api/v1/auth/organizations?limit=0",
                          headers=headers).status_code == 422
        assert client.get("/api/v1/auth/organizations?limit=101",
                          headers=headers).status_code == 422
        page = client.get("/api/v1/auth/organizations?limit=2&offset=0",
                          headers=headers).json()
        assert page["limit"] == 2 and page["offset"] == 0
        assert len(page["items"]) == 2
        assert page["total"] >= 3
        first_ids = [item["id"] for item in page["items"]]
        second = client.get("/api/v1/auth/organizations?limit=2&offset=2",
                            headers=headers).json()
        assert not set(first_ids) & {item["id"] for item in second["items"]}
        # Stable ordering: identical requests return identical pages.
        again = client.get("/api/v1/auth/organizations?limit=2&offset=0",
                           headers=headers).json()
        assert [item["id"] for item in again["items"]] == first_ids
        # Enumeration is exact at any page size: the walk collects every visible
        # organization once and stops there. A missing or repeated row makes
        # "is X listed?" answer depend on which page was asked for, which is how
        # the lifecycle test used to fail once the database outgrew one page.
        snapshot = client.get("/api/v1/auth/organizations?limit=100",
                              headers=headers).json()
        enumerated = walk_organizations(headers, limit=7)
        assert len(enumerated) == snapshot["total"]
        assert len({item["id"] for item in enumerated}) == len(enumerated)
        # Malformed identifiers never reach the database (BE-024 contract).
        assert client.get("/api/v1/auth/organizations/not-a-uuid",
                          headers=headers).status_code == 422
        assert client.patch("/api/v1/auth/projects/not-a-uuid/scope",
                            json={"organization_id": None},
                            headers=headers).status_code == 422
    finally:
        cleanup(user_ids=[str(admin.id)], org_ids=[str(o.id) for o in orgs])


def test_malformed_admin_payloads_rejected():
    admin = global_admin()
    org = create_org("bad-input")
    headers = headers_for(str(admin.id))
    try:
        assert client.patch(f"/api/v1/auth/organizations/{org.id}",
                            json={"name": "   "}, headers=headers).status_code == 422
        assert client.patch(f"/api/v1/auth/organizations/{org.id}",
                            json={"status": "DELETED"}, headers=headers).status_code == 422
        assert client.post(
            f"/api/v1/auth/users/{uuid4()}/roles",
            json={"role_name": "NO_SUCH_ROLE", "scope_type": "GLOBAL"},
            headers=headers).status_code == 404
        assert client.post(
            f"/api/v1/auth/users/{admin.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "ORGANIZATION"},
            headers=headers).status_code == 422  # missing scope id
        assert client.post(
            f"/api/v1/auth/users/{uuid4()}/roles",
            json={"role_name": "REVIEWER", "scope_type": "GALACTIC"},
            headers=headers).status_code == 422  # bad enum
        assert client.post(
            f"/api/v1/auth/users/{uuid4()}/roles",
            json={"role_name": "REVIEWER", "scope_type": "PROJECT",
                  "project_id": "not-a-uuid"},
            headers=headers).status_code == 422
    finally:
        cleanup(user_ids=[str(admin.id)], org_ids=[str(org.id)])


def test_scope_matrix_check_constraint_enforced_by_database():
    """M1: even a repository-level insert that bypasses the service fails."""
    admin = global_admin()
    from backend.db.models import Role as RoleModel

    session = get_session()
    try:
        role_row = session.query(RoleModel).filter(RoleModel.name == "REVIEWER").one()
        with pytest.raises(IntegrityError):
            session.add(UserRoleAssignment(
                user_id=str(admin.id), role_id=str(role_row.id),
                scope_type="ORGANIZATION", organization_id=None))
            session.flush()
        session.rollback()
    finally:
        session.close()
        cleanup(user_ids=[str(admin.id)])


def test_admin_audit_chain_remains_valid():
    admin = global_admin()
    headers = headers_for(str(admin.id))
    try:
        verified = client.get("/api/v1/audit/verify", headers=headers)
        assert verified.status_code == 200
        body = verified.json()
        assert body.get("valid") is True
        assert body.get("failure_count", body.get("failures", 0)) in (0, [])
    finally:
        cleanup(user_ids=[str(admin.id)])


# ---------------------------------------------------------------------------
# OpenAPI accuracy (task section 9)
# ---------------------------------------------------------------------------

#: path -> methods -> error statuses the route can actually return.
DOCUMENTED_ADMIN_ROUTES = {
    "/api/v1/auth/users": {"post": {"401", "403", "409"}, "get": {"401", "403"}},
    "/api/v1/auth/users/{user_id}": {"get": {"401", "403", "404"}},
    "/api/v1/auth/users/{user_id}/status": {"patch": {"401", "403", "404", "409"}},
    "/api/v1/auth/organizations": {"post": {"401", "403"}, "get": {"401", "403"}},
    "/api/v1/auth/organizations/{organization_id}": {
        "get": {"401", "403", "404"}, "patch": {"401", "403", "404"}},
    "/api/v1/auth/organizations/{organization_id}/units": {
        "get": {"401", "403", "404"}, "post": {"401", "403", "404"}},
    "/api/v1/auth/units/{unit_id}": {
        "get": {"401", "403", "404"}, "patch": {"401", "403", "404"}},
    "/api/v1/auth/roles": {"get": {"401", "403"}},
    "/api/v1/auth/permissions": {"get": {"401", "403"}},
    "/api/v1/auth/users/{user_id}/roles": {
        "get": {"401", "403", "404"}, "post": {"401", "403", "404"}},
    "/api/v1/auth/users/{user_id}/roles/{assignment_id}": {
        "delete": {"401", "403", "404", "409"}},
    "/api/v1/auth/clients": {"post": {"401", "403", "404", "409"}},
    "/api/v1/auth/projects/{project_id}/scope": {
        "patch": {"401", "403", "404"}},
    "/api/v1/auth/projects/{project_id}/ownership": {
        "post": {"401", "403", "404"}},
}


def test_openapi_documents_the_administrative_surface():
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]

    for path, methods in DOCUMENTED_ADMIN_ROUTES.items():
        assert path in paths, f"{path} missing from OpenAPI"
        for method, expected_codes in methods.items():
            assert method in paths[path], f"{method.upper()} {path} missing"
            operation = paths[path][method]
            documented = set(operation.get("responses", {}))
            assert expected_codes <= documented, (
                f"{method.upper()} {path} documents {sorted(documented)}, "
                f"expected at least {sorted(expected_codes)}")
            # Every declared error status carries a human-readable description.
            for code in expected_codes:
                assert operation["responses"][code].get("description")
            if method in ("post", "patch"):
                assert operation.get("requestBody"), f"{method.upper()} {path} body"

    # Pagination is part of the published contract on every list route.
    for path in ("/api/v1/auth/users", "/api/v1/auth/organizations",
                 "/api/v1/auth/organizations/{organization_id}/units",
                 "/api/v1/auth/users/{user_id}/roles"):
        params = {p["name"] for p in paths[path]["get"].get("parameters", [])}
        assert {"limit", "offset"} <= params, path

    # No parallel admin API surface was introduced.
    assert not [p for p in paths if "admin-v2" in p]
    # Database models are not exposed: schemas reference Pydantic response
    # models only.
    component_names = set(spec.get("components", {}).get("schemas", {}))
    assert {"OrganizationResponse", "RoleAssignmentListResponse",
            "ProjectScopeUpdate", "OrganizationUpdate", "AdminProjectResponse"} \
        <= component_names
    assert not [name for name in component_names
                if name.startswith(("UserRow", "OrganizationRow"))]
