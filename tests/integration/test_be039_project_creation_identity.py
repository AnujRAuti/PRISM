"""Stage 02-3: POST /projects derives owner, creator and scope, and audits the creation.

The route used to trust its body completely: ``owner_id`` was required and only
checked for existence, so anyone holding ``project.create`` in any scope could
install any user (including a stranger) as a project owner, and the creation
wrote no audit row at all. Scope point P4 says a caller cannot grant ownership or
access merely by supplying another user's id, so the owner now comes from the
authenticated principal unless the caller holds the delegation authority — a
GLOBAL ``project.create`` grant — and the audit actor is always the caller,
because "for whom" and "by whom" are different facts.

The second half is the scope the project is born in. Measured before the fix
(Scratch/deploy1/be019/project_scope_probe.log): an organization-scoped supervisor
could create a project and then could not read it — 201 on POST, 404 on GET, and
its own list came back empty — because POST took no scope, the row was born with
``organization_id IS NULL``, and an ORGANIZATION or PROJECT grant never covers a
NULL-scope resource. Birth scope is therefore derived from the caller's own grant
and never from the body.

Development mode keeps one documented exception, the same one attribution.py makes:
an anonymous request has no verified identity to derive an owner from, so it must
name one, and it cannot claim a scope. Under ``AUTH_MODE=enforcing`` that branch is
unreachable — ``resolve_principal`` returns 401 first.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    ApiClient,
    AuditLedgerEvent,
    Organization,
    OrganizationalUnit,
    Project,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_session
from backend.services import audit_ledger
from backend.services import authorization as auth_service

client = TestClient(app)

BASE = "/api/v1/projects"


@pytest.fixture(autouse=True)
def enforcing_mode():
    """Pin the deployed posture: the development default bypasses these rules."""
    original = settings.auth_mode
    settings.auth_mode = "enforcing"
    try:
        session = get_session()
        try:
            auth_service.ensure_default_catalogue(session)
        finally:
            session.close()
        yield
    finally:
        settings.auth_mode = original


def headers_for(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def client_headers(client_id: str) -> dict:
    return {"Authorization": f"Bearer dev-client-{client_id}"}


class Fixture:
    """Rows created by one test, removable in FK-safe order."""

    def __init__(self):
        self.users: list[str] = []
        self.orgs: list[str] = []
        self.units: list[str] = []
        self.projects: list[str] = []
        self.clients: list[str] = []

    def close(self) -> None:
        session = get_session()
        try:
            if self.users:
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.user_id.in_(self.users)).delete(
                    synchronize_session=False)
            if self.clients:
                session.query(ApiClient).filter(
                    ApiClient.id.in_(self.clients)).delete(synchronize_session=False)
            if self.projects:
                session.query(Project).filter(
                    Project.id.in_(self.projects)).delete(synchronize_session=False)
            if self.units:
                session.query(OrganizationalUnit).filter(
                    OrganizationalUnit.id.in_(self.units)).delete(synchronize_session=False)
            if self.orgs:
                session.query(Organization).filter(
                    Organization.id.in_(self.orgs)).delete(synchronize_session=False)
            if self.users:
                session.query(User).filter(User.id.in_(self.users)).delete(
                    synchronize_session=False)
            session.commit()
        finally:
            session.close()


@pytest.fixture
def rows():
    made = Fixture()
    yield made
    made.close()


def make_user(rows: Fixture, label: str, *, status: str = "ACTIVE") -> str:
    session = get_session()
    try:
        row = User(username=f"be039-{label}-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@be039.test", status=status,
                   is_active=status == "ACTIVE")
        session.add(row)
        session.commit()
        rows.users.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_org(rows: Fixture, label: str, *, status: str = "ACTIVE") -> str:
    session = get_session()
    try:
        row = Organization(name=f"BE039 {label} {uuid4().hex[:6]}",
                           code=f"BE039-{label}-{uuid4().hex[:8]}", status=status)
        session.add(row)
        session.commit()
        rows.orgs.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_unit(rows: Fixture, organization_id: str, label: str) -> str:
    session = get_session()
    try:
        row = OrganizationalUnit(organization_id=organization_id,
                                 name=f"BE039 {label} {uuid4().hex[:6]}",
                                 code=f"BE039-{label}-{uuid4().hex[:8]}", status="ACTIVE")
        session.add(row)
        session.commit()
        rows.units.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_project_row(rows: Fixture, owner_id: str,
                     organization_id: str | None = None) -> str:
    session = get_session()
    try:
        row = Project(name=f"be039 seed {uuid4().hex[:6]}", owner_id=owner_id,
                      organization_id=organization_id)
        session.add(row)
        session.commit()
        rows.projects.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_api_client(rows: Fixture, *, scopes: list[str],
                    project_id: str | None = None) -> str:
    session = get_session()
    try:
        row = ApiClient(name=f"be039-client-{uuid4().hex[:8]}", scopes=scopes,
                        project_id=project_id, status="ACTIVE")
        session.add(row)
        session.commit()
        rows.clients.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def grant(user_id: str, role_name: str, scope_type: str, *,
          organization_id: str | None = None, unit_id: str | None = None,
          project_id: str | None = None) -> None:
    """SUPERVISOR alone holds project.create; ADMINISTRATOR alone holds
    organization.manage, so the role choice decides which guard is being tested."""
    session = get_session()
    try:
        auth_service.assign_role(session, user_id=user_id, role_name=role_name,
                                 scope_type=scope_type, organization_id=organization_id,
                                 organizational_unit_id=unit_id, project_id=project_id)
        session.commit()
    finally:
        session.close()


def named_project_count(name: str) -> int:
    session = get_session()
    try:
        return session.query(Project).filter(Project.name == name).count()
    finally:
        session.close()


def row_of(project_id: str):
    session = get_session()
    try:
        return session.query(Project).filter(Project.id == project_id).one_or_none()
    finally:
        session.close()


def ledger(event_type: str, resource_id: str):
    session = get_session()
    try:
        return session.query(AuditLedgerEvent).filter(
            AuditLedgerEvent.event_type == event_type,
            AuditLedgerEvent.resource_id == resource_id).all()
    finally:
        session.close()


def test_owner_defaults_to_the_principal_and_stays_visible(rows):
    """Contract 1 + the measured 404-on-own-project defect.

    A body value cannot name the scope, so the caller's own ORGANIZATION grant
    decides where the project is born — which is what makes it readable by the
    caller that created it.
    """
    supervisor = make_user(rows, "sup-a")
    org_a = make_org(rows, "a")
    grant(supervisor, "SUPERVISOR", "ORGANIZATION", organization_id=org_a)
    headers = headers_for(supervisor)
    name = f"be039 self {uuid4().hex[:8]}"

    created = client.post(BASE, headers=headers, json={"name": name})
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    rows.projects.append(project_id)

    assert created.json()["owner_id"] == supervisor
    stored = row_of(project_id)
    assert str(stored.organization_id) == org_a
    assert stored.organizational_unit_id is None

    read = client.get(f"{BASE}/{project_id}", headers=headers)
    assert read.status_code == 200, read.text
    listed = client.get(BASE, headers=headers, params={"limit": 100})
    assert project_id in {item["id"] for item in listed.json()["items"]}


def test_delegating_ownership_requires_global_project_create(rows):
    """Contract 2 + 3: an id in the body is not a permission.

    Non-vacuity: the refused caller's own self-create is exercised in the same
    test, so the refusal can only be explained by the named owner, and the
    refused name is checked for absence in ``projects`` rather than trusted to
    the status code alone.
    """
    org_supervisor = make_user(rows, "sup-org")
    global_supervisor = make_user(rows, "sup-glob")
    peer = make_user(rows, "peer")
    org_a = make_org(rows, "a")
    grant(org_supervisor, "SUPERVISOR", "ORGANIZATION", organization_id=org_a)
    grant(global_supervisor, "SUPERVISOR", "GLOBAL")

    refused_name = f"be039 refused {uuid4().hex[:8]}"
    refused = client.post(BASE, headers=headers_for(org_supervisor),
                          json={"name": refused_name, "owner_id": peer})
    assert refused.status_code == 403, refused.text
    assert named_project_count(refused_name) == 0

    self_name = f"be039 own {uuid4().hex[:8]}"
    own = client.post(BASE, headers=headers_for(org_supervisor), json={"name": self_name})
    assert own.status_code == 201, own.text
    own_id = own.json()["id"]
    rows.projects.append(own_id)
    assert own.json()["owner_id"] == org_supervisor

    delegated_name = f"be039 delegated {uuid4().hex[:8]}"
    delegated = client.post(BASE, headers=headers_for(global_supervisor),
                            json={"name": delegated_name, "owner_id": peer})
    assert delegated.status_code == 201, delegated.text
    delegated_id = delegated.json()["id"]
    rows.projects.append(delegated_id)
    assert delegated.json()["owner_id"] == peer
    # A GLOBAL caller holds no single organization, so the project stays platform-wide.
    stored = row_of(delegated_id)
    assert stored.organization_id is None

    events = ledger("PROJECT_CREATED", delegated_id)
    assert len(events) == 1
    event = events[0]
    assert str(event.actor_id) == global_supervisor
    payload = event.payload or {}
    assert payload["owner_id"] == peer
    assert payload["created_by"] == global_supervisor


def test_owner_must_exist_and_be_active(rows):
    """Target-user validation, mirroring the ownership-transfer rules.

    Only a caller holding the delegation authority reaches the target lookup, so
    the existence and status assertions run under a GLOBAL grant. The
    organization-scoped caller is exercised on the same unknown id first: it must
    be refused for lack of authority, which is also what keeps the route from
    confirming or denying that a target user id exists. Both refusals use the
    name-shape probe as the delegation test: a 404 or 422 that still wrote the
    row would still look like a refusal.
    """
    org_supervisor = make_user(rows, "sup-valid")
    global_supervisor = make_user(rows, "sup-global")
    org = make_org(rows, "v")
    grant(org_supervisor, "SUPERVISOR", "ORGANIZATION", organization_id=org)
    grant(global_supervisor, "SUPERVISOR", "GLOBAL")

    ghost = str(uuid4())

    gated_name = f"be039 gated {uuid4().hex[:8]}"
    gated = client.post(BASE, headers=headers_for(org_supervisor),
                        json={"name": gated_name, "owner_id": ghost})
    assert gated.status_code == 403, gated.text
    assert "GLOBAL" in gated.json()["detail"]
    assert named_project_count(gated_name) == 0

    headers = headers_for(global_supervisor)
    ghost_name = f"be039 ghost {uuid4().hex[:8]}"
    missing = client.post(BASE, headers=headers,
                          json={"name": ghost_name, "owner_id": ghost})
    assert missing.status_code == 404, missing.text
    assert missing.json()["detail"] == "Owner not found"
    assert named_project_count(ghost_name) == 0

    dormant = make_user(rows, "suspended", status="SUSPENDED")
    inactive_name = f"be039 inactive {uuid4().hex[:8]}"
    inactive = client.post(BASE, headers=headers,
                           json={"name": inactive_name, "owner_id": dormant})
    assert inactive.status_code == 422, inactive.text
    assert named_project_count(inactive_name) == 0


def test_unit_scoped_creator_is_born_inside_the_unit(rows):
    """The derivation is a single grant, not a guess: one unit wins, ambiguity does not."""
    supervisor = make_user(rows, "sup-unit")
    org = make_org(rows, "unit-parent")
    unit = make_unit(rows, org, "u1")
    grant(supervisor, "SUPERVISOR", "ORGANIZATIONAL_UNIT", unit_id=unit)

    created = client.post(BASE, headers=headers_for(supervisor),
                          json={"name": f"be039 unit {uuid4().hex[:8]}"})
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    rows.projects.append(project_id)

    stored = row_of(project_id)
    assert str(stored.organizational_unit_id) == unit
    assert str(stored.organization_id) == org
    assert client.get(f"{BASE}/{project_id}", headers=headers_for(supervisor)).status_code == 200

    # A caller holding two organization grants has no single derivable scope.
    divided = make_user(rows, "sup-two")
    org_b = make_org(rows, "b")
    grant(divided, "SUPERVISOR", "ORGANIZATION", organization_id=org)
    grant(divided, "SUPERVISOR", "ORGANIZATION", organization_id=org_b)
    both = client.post(BASE, headers=headers_for(divided),
                       json={"name": f"be039 divided {uuid4().hex[:8]}"})
    assert both.status_code == 201, both.text
    both_id = both.json()["id"]
    rows.projects.append(both_id)
    assert row_of(both_id).organization_id is None


def test_api_client_callers_cannot_invent_an_owner(rows):
    """An API client has no ``users`` row, so it can only delegate, and only globally."""
    target = make_user(rows, "client-target")
    project_bound = make_user(rows, "client-owner")
    bound_project = make_project_row(rows, project_bound)
    platform_client = make_api_client(rows, scopes=["project.create"])
    bound_client = make_api_client(rows, scopes=["project.create"],
                                   project_id=bound_project)

    unnamed = client.post(BASE, headers=client_headers(platform_client),
                          json={"name": f"be039 client none {uuid4().hex[:8]}"})
    assert unnamed.status_code == 422, unnamed.text
    assert "owner_id is required" in unnamed.json()["detail"]

    wide_name = f"be039 client wide {uuid4().hex[:8]}"
    wide = client.post(BASE, headers=client_headers(platform_client),
                       json={"name": wide_name, "owner_id": target})
    assert wide.status_code == 201, wide.text
    wide_id = wide.json()["id"]
    rows.projects.append(wide_id)
    events = ledger("PROJECT_CREATED", wide_id)
    assert len(events) == 1
    # The client id is the recorded creator: ledger.actor_id carries no users FK,
    # and a machine caller is still an accountable one.
    assert str(events[0].actor_id) == platform_client
    assert (events[0].payload or {})["created_by"] == platform_client

    narrow_name = f"be039 client narrow {uuid4().hex[:8]}"
    narrow = client.post(BASE, headers=client_headers(bound_client),
                         json={"name": narrow_name, "owner_id": target})
    assert narrow.status_code == 403, narrow.text
    assert named_project_count(narrow_name) == 0


def test_creation_and_audit_roll_back_together(rows, monkeypatch):
    """Contract 4: the project and its PROJECT_CREATED record are one transaction."""
    supervisor = make_user(rows, "sup-atomic")
    org = make_org(rows, "atomic")
    grant(supervisor, "SUPERVISOR", "ORGANIZATION", organization_id=org)

    def refuse_append(*args, **kwargs):
        raise RuntimeError("audit writer unavailable")

    monkeypatch.setattr(audit_ledger, "append_event", refuse_append)
    name = f"be039 rolled back {uuid4().hex[:8]}"
    with pytest.raises(RuntimeError):
        client.post(BASE, headers=headers_for(supervisor), json={"name": name})
    assert named_project_count(name) == 0

    # Same request, writer restored: proves the absence above was the rollback.
    monkeypatch.undo()
    created = client.post(BASE, headers=headers_for(supervisor), json={"name": name})
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    rows.projects.append(project_id)
    assert len(ledger("PROJECT_CREATED", project_id)) == 1


def test_development_anonymous_caller_must_name_an_owner(rows):
    """The one documented exception, and it still cannot claim a scope."""
    user = make_user(rows, "dev-owner")
    name = f"be039 dev anon {uuid4().hex[:8]}"
    settings.auth_mode = "development"
    try:
        unnamed = client.post(BASE, json={"name": f"be039 dev none {uuid4().hex[:8]}"})
        assert unnamed.status_code == 422, unnamed.text

        created = client.post(BASE, json={"name": name, "owner_id": user})
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]
        rows.projects.append(project_id)
        assert created.json()["owner_id"] == user
        assert row_of(project_id).organization_id is None
        # Nothing verified exists to attribute, so the ledger carries no actor.
        assert (ledger("PROJECT_CREATED", project_id)[0].payload or {})["created_by"] is None
    finally:
        settings.auth_mode = "enforcing"


def test_ownership_transfer_needs_global_authority(rows):
    """The destination half of the same rule, on the admin transfer route.

    The route guard already pins organization.manage over the project's current
    scope; this proves it no longer stops there, so a scoped administrator cannot
    hand the project to an arbitrary user id.
    """
    owner = make_user(rows, "old-owner")
    stranger = make_user(rows, "stranger")
    org = make_org(rows, "transfer")
    project_id = make_project_row(rows, owner, org)

    org_admin = make_user(rows, "admin-org")
    global_admin = make_user(rows, "admin-glob")
    grant(org_admin, "ADMINISTRATOR", "ORGANIZATION", organization_id=org)
    grant(global_admin, "ADMINISTRATOR", "GLOBAL")

    refused = client.post(f"/api/v1/auth/projects/{project_id}/ownership",
                          headers=headers_for(org_admin), json={"owner_id": stranger})
    assert refused.status_code == 403, refused.text
    assert str(row_of(project_id).owner_id) == owner

    allowed = client.post(f"/api/v1/auth/projects/{project_id}/ownership",
                          headers=headers_for(global_admin), json={"owner_id": stranger})
    assert allowed.status_code == 200, allowed.text
    assert str(row_of(project_id).owner_id) == stranger
    events = ledger("PROJECT_OWNERSHIP_CHANGED", project_id)
    assert len(events) == 1
    assert str(events[0].actor_id) == global_admin
