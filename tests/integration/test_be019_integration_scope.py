"""Stage 02-3 (§8.4): the BE-019 read and write families are scoped, not merely gated.

The scope classification's §4.2 measured five integration collections guarded by
a resource-less ``require(action)``: a permission held in *any* scope opened the
whole table, and the only filters were the caller's own query parameters — which
is the caller choosing what to read, not authorization. Owner policy P1/P2 says
project resources stay inside authorized projects and organization resources
inside the principal's organization unless a grant is explicitly platform-wide.
Four of the five are now scoped in SQL (clients by project, systems, webhooks and
references by organization — the last two through the NOT NULL foreign key to
their external system). ``events`` stays unfiltered and documented as GAP-SCHEMA
because its ``project_id`` has no foreign key, so filtering it would authorize
through an unvalidated column.

The same rule applies on the way in: a caller cannot acquire authority over a
resource's scope just by supplying that scope's id in the body. Creating an
external system needs ``integration.manage`` for the named organization, creating
a client needs ``api_client.manage`` for the named project, and an id-less
(platform-wide) create needs the GLOBAL grant — a resource id existing is not a
permission. Denied creates are checked against the row counts afterwards, because
a refusal that still wrote the row would still look like a refusal.

Non-vacuity: each absence is paired with the same row being listed for an
authorized caller in the same test, so a missing row can only be explained by
scope. Revocation is checked against ``revoked_at`` afterwards, because the
route's authorization refusal (404) and its own not-found path (404) share a
status code.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    ApiClient,
    ApiCredential,
    AuditLedgerEvent,
    ExternalReference,
    ExternalSystem,
    Organization,
    Project,
    User,
    UserRoleAssignment,
    WebhookSubscription,
)
from backend.db.session import get_session
from backend.services import authorization as auth_service


client = TestClient(app)

BASE = "/api/v1/integrations"


@pytest.fixture(autouse=True)
def enforcing():
    """Pin the deployed posture: under the development default an anonymous
    caller bypasses the very scope rules these tests measure."""
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


class Fixture:
    """Rows created by one test, removable in FK-safe order."""

    def __init__(self):
        self.users: list[str] = []
        self.orgs: list[str] = []
        self.projects: list[str] = []
        self.systems: list[str] = []
        self.clients: list[str] = []
        self.credentials: list[str] = []
        self.webhooks: list[str] = []
        self.references: list[str] = []

    def close(self) -> None:
        session = get_session()
        try:
            if self.users:
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.user_id.in_(self.users)).delete(
                    synchronize_session=False)
            if self.credentials:
                session.query(ApiCredential).filter(
                    ApiCredential.id.in_(self.credentials)).delete(synchronize_session=False)
            if self.webhooks:
                session.query(WebhookSubscription).filter(
                    WebhookSubscription.id.in_(self.webhooks)).delete(synchronize_session=False)
            if self.references:
                # RESTRICT on external_system_id: the child rows must go first.
                session.query(ExternalReference).filter(
                    ExternalReference.id.in_(self.references)).delete(synchronize_session=False)
            if self.clients:
                session.query(ApiClient).filter(
                    ApiClient.id.in_(self.clients)).delete(synchronize_session=False)
            if self.systems:
                session.query(ExternalSystem).filter(
                    ExternalSystem.id.in_(self.systems)).delete(synchronize_session=False)
            if self.projects:
                session.query(Project).filter(
                    Project.id.in_(self.projects)).delete(synchronize_session=False)
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
def fixture_rows():
    rows = Fixture()
    yield rows
    rows.close()


def make_user(fx: Fixture, label: str) -> str:
    session = get_session()
    try:
        row = User(username=f"be019-{label}-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@be019.test")
        session.add(row)
        session.commit()
        fx.users.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_org(fx: Fixture, label: str) -> str:
    session = get_session()
    try:
        row = Organization(name=f"BE019 {label} {uuid4().hex[:6]}",
                           code=f"BE019-{label}-{uuid4().hex[:8]}", status="ACTIVE")
        session.add(row)
        session.commit()
        fx.orgs.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_project(fx: Fixture, owner_id: str, organization_id: str | None = None) -> str:
    session = get_session()
    try:
        row = Project(name=f"be019 {uuid4().hex[:6]}", owner_id=owner_id,
                      organization_id=organization_id)
        session.add(row)
        session.commit()
        fx.projects.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_system(fx: Fixture, organization_id: str | None) -> str:
    session = get_session()
    try:
        row = ExternalSystem(organization_id=organization_id,
                             name=f"be019 system {uuid4().hex[:6]}",
                             code=f"be019-{uuid4().hex[:12]}",
                             system_type="FIELD_SYSTEM", status="ACTIVE", metadata_={})
        session.add(row)
        session.commit()
        fx.systems.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_client_row(fx: Fixture, project_id: str | None) -> str:
    session = get_session()
    try:
        row = ApiClient(name=f"be019-client-{uuid4().hex[:8]}", scopes=[],
                        project_id=project_id, status="ACTIVE")
        session.add(row)
        session.commit()
        fx.clients.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_credential(fx: Fixture, client_id: str) -> str:
    session = get_session()
    try:
        row = ApiCredential(client_id=client_id, credential_hash=f"sha256${uuid4().hex}")
        session.add(row)
        session.commit()
        fx.credentials.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_webhook(fx: Fixture, external_system_id: str) -> str:
    session = get_session()
    try:
        row = WebhookSubscription(
            external_system_id=external_system_id,
            endpoint_url="http://127.0.0.1:9/ignored",
            subscribed_events=["EVIDENCE_UPLOADED"],
            secret_hash=f"sha256${uuid4().hex}",
            status="ACTIVE",
        )
        session.add(row)
        session.commit()
        fx.webhooks.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_reference(fx: Fixture, external_system_id: str) -> str:
    session = get_session()
    try:
        row = ExternalReference(external_system_id=external_system_id,
                                resource_type="EVIDENCE",
                                resource_id=str(uuid4()),
                                external_id=f"be019-{uuid4().hex[:12]}")
        session.add(row)
        session.commit()
        fx.references.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def grant(user_id: str, scope_type: str, *, organization_id: str | None = None,
          project_id: str | None = None) -> None:
    """Administrator is the only role holding the integration permission family
    (integration/api_client/credential/webhook/external_data), so every grant
    here varies only the *scope*."""
    session = get_session()
    try:
        auth_service.assign_role(session, user_id=user_id, role_name="ADMINISTRATOR",
                                 scope_type=scope_type, organization_id=organization_id,
                                 project_id=project_id)
        session.commit()
    finally:
        session.close()


def listed(path: str, token: dict) -> set[str]:
    response = client.get(path, headers=token, params={"limit": 100})
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()}


def test_system_list_is_limited_to_the_callers_organization(fixture_rows):
    """P2: a non-GLOBAL integration.read holder sees their own systems only."""
    org_a = make_org(fixture_rows, "alpha")
    org_b = make_org(fixture_rows, "beta")
    system_a = make_system(fixture_rows, org_a)
    system_b = make_system(fixture_rows, org_b)
    system_unscoped = make_system(fixture_rows, None)

    admin_a = make_user(fixture_rows, "org-a-admin")
    grant(admin_a, "ORGANIZATION", organization_id=org_a)
    global_admin = make_user(fixture_rows, "global-admin")
    grant(global_admin, "GLOBAL")

    mine = listed(f"{BASE}/systems", headers_for(admin_a))
    assert system_a in mine
    assert system_b not in mine
    assert system_unscoped not in mine
    # The caller-supplied filter can only narrow the authorized set: naming
    # another organization cannot reach the rows that live there.
    forced = client.get(f"{BASE}/systems", headers=headers_for(admin_a),
                        params={"organization_id": org_b, "limit": 100})
    assert forced.status_code == 200, forced.text
    assert forced.json() == []

    # Positive control: all three rows exist and are listable by GLOBAL.
    everything = listed(f"{BASE}/systems", headers_for(global_admin))
    assert {system_a, system_b, system_unscoped} <= everything


def test_client_list_is_limited_to_the_callers_project(fixture_rows):
    """P1: a project-scoped holder enumerates only clients bound to their project."""
    org_a = make_org(fixture_rows, "alpha")
    owner = make_user(fixture_rows, "owner")
    project_a = make_project(fixture_rows, owner, org_a)
    project_b = make_project(fixture_rows, owner, org_a)
    client_a = make_client_row(fixture_rows, project_a)
    client_b = make_client_row(fixture_rows, project_b)
    client_unscoped = make_client_row(fixture_rows, None)

    admin_a = make_user(fixture_rows, "proj-a-admin")
    grant(admin_a, "PROJECT", project_id=project_a)
    global_admin = make_user(fixture_rows, "global-admin")
    grant(global_admin, "GLOBAL")

    mine = listed(f"{BASE}/clients", headers_for(admin_a))
    assert client_a in mine
    assert client_b not in mine
    # A client with no project acts platform-wide: it is not a project row.
    assert client_unscoped not in mine

    everything = listed(f"{BASE}/clients", headers_for(global_admin))
    assert {client_a, client_b, client_unscoped} <= everything
    # The item route already agreed with the collection: same row, same verdict.
    assert client.get(f"{BASE}/clients/{client_b}", headers=headers_for(admin_a)).status_code == 404
    assert client.get(f"{BASE}/clients/{client_a}", headers=headers_for(admin_a)).status_code == 200


def test_webhook_list_inherits_the_external_systems_organization(fixture_rows):
    """A subscription has no scope column, so it is readable where its system is."""
    org_a = make_org(fixture_rows, "alpha")
    org_b = make_org(fixture_rows, "beta")
    system_a = make_system(fixture_rows, org_a)
    system_b = make_system(fixture_rows, org_b)
    webhook_a = make_webhook(fixture_rows, system_a)
    webhook_b = make_webhook(fixture_rows, system_b)

    admin_a = make_user(fixture_rows, "org-a-admin")
    grant(admin_a, "ORGANIZATION", organization_id=org_a)
    global_admin = make_user(fixture_rows, "global-admin")
    grant(global_admin, "GLOBAL")

    mine = listed(f"{BASE}/webhooks", headers_for(admin_a))
    assert webhook_a in mine
    assert webhook_b not in mine

    everything = listed(f"{BASE}/webhooks", headers_for(global_admin))
    assert {webhook_a, webhook_b} <= everything


def test_project_grant_reaches_no_organization_level_rows(fixture_rows):
    """Fail closed rather than escalate: a project grant names no organization."""
    org_a = make_org(fixture_rows, "alpha")
    owner = make_user(fixture_rows, "owner")
    project_a = make_project(fixture_rows, owner, org_a)
    system_a = make_system(fixture_rows, org_a)
    webhook_a = make_webhook(fixture_rows, system_a)

    project_admin = make_user(fixture_rows, "project-admin")
    grant(project_admin, "PROJECT", project_id=project_a)
    global_admin = make_user(fixture_rows, "global-admin")
    grant(global_admin, "GLOBAL")

    # Both rows are readable by GLOBAL, so the emptiness below is authorization.
    assert {system_a, webhook_a} <= (
        listed(f"{BASE}/systems", headers_for(global_admin))
        | listed(f"{BASE}/webhooks", headers_for(global_admin))
    )
    assert system_a not in listed(f"{BASE}/systems", headers_for(project_admin))
    assert webhook_a not in listed(f"{BASE}/webhooks", headers_for(project_admin))
    # The project-scoped client listing still works, so the grant is real.
    assert "integration.read" in _permissions(project_admin)


def test_credential_revoke_is_scoped_to_the_clients_project(fixture_rows):
    """Issuing a credential already checks the client's scope; revoking must too."""
    org_a = make_org(fixture_rows, "alpha")
    owner = make_user(fixture_rows, "owner")
    project_a = make_project(fixture_rows, owner, org_a)
    project_b = make_project(fixture_rows, owner, org_a)
    client_a = make_client_row(fixture_rows, project_a)
    client_b = make_client_row(fixture_rows, project_b)
    credential_a = make_credential(fixture_rows, client_a)
    credential_b = make_credential(fixture_rows, client_b)

    admin_b = make_user(fixture_rows, "proj-b-admin")
    grant(admin_b, "PROJECT", project_id=project_b)
    global_admin = make_user(fixture_rows, "global-admin")
    grant(global_admin, "GLOBAL")

    # Same permission, same route, different target project: only scope differs.
    refused = client.post(f"{BASE}/credentials/{credential_a}/revoke", headers=headers_for(admin_b))
    assert refused.status_code == 404
    assert _revoked_at(credential_a) is None, "refusal must not have touched the row"

    allowed = client.post(f"{BASE}/credentials/{credential_b}/revoke", headers=headers_for(admin_b))
    assert allowed.status_code == 200, allowed.text
    assert _revoked_at(credential_b) is not None

    cross_check = client.post(f"{BASE}/credentials/{credential_a}/revoke",
                              headers=headers_for(global_admin))
    assert cross_check.status_code == 200, cross_check.text
    assert _revoked_at(credential_a) is not None


def test_client_create_cannot_target_another_project(fixture_rows):
    """P1 on the way in: naming a project id does not grant authority over it."""
    org_a = make_org(fixture_rows, "alpha")
    owner = make_user(fixture_rows, "owner")
    project_a = make_project(fixture_rows, owner, org_a)
    project_b = make_project(fixture_rows, owner, org_a)

    admin_a = make_user(fixture_rows, "proj-a-admin")
    grant(admin_a, "PROJECT", project_id=project_a)
    global_admin = make_user(fixture_rows, "global-admin")
    grant(global_admin, "GLOBAL")

    name = f"be019-denied-{uuid4().hex[:8]}"
    before_b = _client_count(project_b)
    refused = client.post(f"{BASE}/clients", headers=headers_for(admin_a),
                          json={"name": name, "project_id": project_b, "scopes": []})
    assert refused.status_code == 404, refused.text
    assert _client_count(project_b) == before_b, "denied create must write nothing"

    # A project id that does not exist is not a back door either: the guard runs
    # before the insert, so the foreign key is never reached.
    ghost = client.post(f"{BASE}/clients", headers=headers_for(admin_a),
                        json={"name": f"be019-ghost-{uuid4().hex[:8]}",
                              "project_id": str(uuid4()), "scopes": []})
    assert ghost.status_code == 404, ghost.text

    # No project means a platform-wide client, and its credential works against
    # every project — so it needs the GLOBAL grant, not merely api_client.manage.
    platform = client.post(f"{BASE}/clients", headers=headers_for(admin_a),
                           json={"name": f"be019-wide-{uuid4().hex[:8]}", "scopes": []})
    assert platform.status_code == 404, platform.text

    before_a = _client_count(project_a)
    created = client.post(f"{BASE}/clients", headers=headers_for(admin_a),
                          json={"name": f"be019-own-{uuid4().hex[:8]}",
                                "project_id": project_a, "scopes": ["read"]})
    assert created.status_code == 201, created.text
    row = created.json()
    fixture_rows.clients.append(row["id"])
    # The counter above is not inert: the authorized create moves it by exactly one.
    assert _client_count(project_a) == before_a + 1
    assert row["project_id"] == project_a

    event = _ledger("API_CLIENT_CREATED", row["id"])
    assert event is not None, "creation must leave an audit record"
    assert event.actor_id == admin_a, "actor comes from the authenticated principal"
    assert event.project_id == project_a, "the ledger carries the authorized scope"

    wide = client.post(f"{BASE}/clients", headers=headers_for(global_admin),
                       json={"name": f"be019-wide-ok-{uuid4().hex[:8]}", "scopes": []})
    assert wide.status_code == 201, wide.text
    fixture_rows.clients.append(wide.json()["id"])
    assert wide.json()["project_id"] is None


def test_system_create_cannot_target_another_organization(fixture_rows):
    """P2 on the way in: an organization id in the body is a claim, not a grant."""
    org_a = make_org(fixture_rows, "alpha")
    org_b = make_org(fixture_rows, "beta")

    admin_a = make_user(fixture_rows, "org-a-admin")
    grant(admin_a, "ORGANIZATION", organization_id=org_a)
    global_admin = make_user(fixture_rows, "global-admin")
    grant(global_admin, "GLOBAL")

    before_b = _system_count(org_b)
    refused = client.post(f"{BASE}/systems", headers=headers_for(admin_a),
                          json={"name": "be019 denied", "code": f"be019d{uuid4().hex[:8]}",
                                "system_type": "FIELD_SYSTEM", "organization_id": org_b})
    assert refused.status_code == 404, refused.text
    assert _system_count(org_b) == before_b, "denied create must write nothing"

    # An organization-less system is platform-wide configuration.
    platform = client.post(f"{BASE}/systems", headers=headers_for(admin_a),
                           json={"name": "be019 wide", "code": f"be019w{uuid4().hex[:8]}",
                                 "system_type": "FIELD_SYSTEM"})
    assert platform.status_code == 404, platform.text

    before_a = _system_count(org_a)
    created = client.post(f"{BASE}/systems", headers=headers_for(admin_a),
                          json={"name": "be019 own", "code": f"be019o{uuid4().hex[:8]}",
                                "system_type": "FIELD_SYSTEM", "organization_id": org_a})
    assert created.status_code == 201, created.text
    row = created.json()
    fixture_rows.systems.append(row["id"])
    assert _system_count(org_a) == before_a + 1

    event = _ledger("EXTERNAL_SYSTEM_CREATED", row["id"])
    assert event is not None, "creation must leave an audit record"
    assert event.actor_id == admin_a, "actor comes from the authenticated principal"
    # The ledger has no organization column, so the authorized target scope has
    # to be inside the payload or the record cannot be checked later.
    assert (event.payload or {}).get("organization_id") == org_a

    wide = client.post(f"{BASE}/systems", headers=headers_for(global_admin),
                       json={"name": "be019 wide ok", "code": f"be019g{uuid4().hex[:8]}",
                             "system_type": "FIELD_SYSTEM"})
    assert wide.status_code == 201, wide.text
    fixture_rows.systems.append(wide.json()["id"])
    assert wide.json()["organization_id"] is None


def test_reference_list_inherits_the_external_systems_organization(fixture_rows):
    """References resolve ownership through the same foreign key as webhooks."""
    org_a = make_org(fixture_rows, "alpha")
    org_b = make_org(fixture_rows, "beta")
    reference_a = make_reference(fixture_rows, make_system(fixture_rows, org_a))
    reference_b = make_reference(fixture_rows, make_system(fixture_rows, org_b))
    reference_platform = make_reference(fixture_rows, make_system(fixture_rows, None))

    admin_a = make_user(fixture_rows, "org-a-admin")
    grant(admin_a, "ORGANIZATION", organization_id=org_a)
    global_admin = make_user(fixture_rows, "global-admin")
    grant(global_admin, "GLOBAL")

    mine = listed(f"{BASE}/references", headers_for(admin_a))
    assert reference_a in mine
    assert reference_b not in mine
    # Platform-wide rows stay GLOBAL-only: the join must not expose them, and it
    # must not redefine their visibility either — GLOBAL still lists them.
    assert reference_platform not in mine

    everything = listed(f"{BASE}/references", headers_for(global_admin))
    assert {reference_a, reference_b, reference_platform} <= everything


def _permissions(user_id: str) -> set[str]:
    from backend.services.authorization import resolve_user_principal

    session = get_session()
    try:
        return set(resolve_user_principal(session, user_id).permissions)
    finally:
        session.close()


def _revoked_at(credential_id: str):
    session = get_session()
    try:
        row = session.query(ApiCredential).filter(ApiCredential.id == credential_id).one()
        return row.revoked_at
    finally:
        session.close()


def _client_count(project_id: str | None) -> int:
    session = get_session()
    try:
        return (session.query(ApiClient)
                .filter(ApiClient.project_id == project_id).count())
    finally:
        session.close()


def _system_count(organization_id: str | None) -> int:
    session = get_session()
    try:
        return (session.query(ExternalSystem)
                .filter(ExternalSystem.organization_id == organization_id).count())
    finally:
        session.close()


def _ledger(event_type: str, resource_id: str):
    session = get_session()
    try:
        return (session.query(AuditLedgerEvent)
                .filter(AuditLedgerEvent.event_type == event_type,
                        AuditLedgerEvent.resource_id == resource_id)
                .one_or_none())
    finally:
        session.close()
