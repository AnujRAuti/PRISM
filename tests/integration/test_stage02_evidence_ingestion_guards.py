"""M-BE-01 step 3: the three evidence-ingestion defects that were P0, each proven at the HTTP layer.

The 2026-10-16 acceptance register left rows 2.1, 2.2 and 2.6 open on the two
evidence-ingestion routes. Each had the same shape: the route *appeared* to be
governed, but the governing value was taken from the caller, dropped one call
down, or never read at all.

- **2.1 (P0, authorization)** — `POST /integrations/evidence` wrote a
  caller-supplied ``project_id`` onto the new evidence row with only a
  resource-less ``require("external_data.write")`` in front of it. A grant held
  for one project could therefore drop external evidence into another
  organization's project. The fix is the guard `PATCH /evidence/{id}/context`
  already used for the same operation: the target must be inside the caller's
  visible projects, and an unreachable target answers 404 so the refusal never
  confirms the project exists.
- **2.2 (P0, attribution)** — every upload wrote its `EVIDENCE_UPLOADED` ledger
  row with ``actor_id=None`` even though each caller held a verified principal.
  `ingest_evidence` never received one. The uploader is now the caller's
  principal id, threaded through all four call sites.
- **2.6 (P0, contract honesty)** — `Idempotency-Key` was declared on the route
  and never read, so a retry after a lost response silently created a second
  evidence row and a second quarantine object. Enforcement is what the owner
  decided on 2026-10-16 ("enforce the documented keys with deterministic replay
  and reject conflicting reuse"). The key store's ``client_id`` is a NOT NULL
  foreign key to ``api_clients.id`` (read off the database, not inferred from
  the model), so only an API-client credential can hold a key — a human caller
  that sends the header is refused rather than quietly left unguarded.

Non-vacuity: each refusal is paired with the *same* caller and the *same*
permission succeeding against a target it does control, and every denial
re-counts the rows afterwards, because a refusal that still wrote the row would
still look like a refusal. The replay test asserts one `Evidence` row *and* one
ledger row for two requests: a deduplicated response backed by a second insert
would otherwise pass.

Deliberately **not** covered here, because the owner's open decision — not the
code — is what blocks them: the quarantine lifecycle and read filter (2.3,
needs a migration plus a backfill call), an uploader *column* on `evidence`
(needs a migration), and retry dedupe for `POST /evidence`, whose header is not
documented today and whose retry semantics clients have not agreed to.
"""

from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import or_

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    ApiClient,
    ApiCredential,
    AuditLedgerEvent,
    Evidence,
    ExternalAssertion,
    ExternalReference,
    ExternalSystem,
    IdempotencyKey,
    Organization,
    Project,
    User,
    UserRoleAssignment,
    WebhookSubscription,
)
from backend.db.session import get_session
from backend.services import authorization as auth_service
from backend.services.storage import StorageService


client = TestClient(app)

BASE = "/api/v1/integrations"


@pytest.fixture(autouse=True)
def enforcing():
    """Pin the deployed posture: under the development default an anonymous
    caller bypasses the very guards these tests measure."""
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


def user_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def client_headers(client_id: str) -> dict:
    """A dev-client token resolves to the same API_CLIENT principal a real
    credential does, without putting a secret in the test."""
    return {"Authorization": f"Bearer dev-client-{client_id}"}


def image_bytes(image_format: str = "JPEG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(20, 120, 220)).save(output, format=image_format)
    return output.getvalue()


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
        self.assertions: list[str] = []
        self.evidence: list[tuple[str, str]] = []

    def close(self) -> None:
        for _, storage_key in self.evidence:
            try:
                storage = StorageService()
                storage.delete_object(storage.quarantine_bucket, storage_key)
            except Exception:
                pass
        session = get_session()
        try:
            if self.evidence:
                session.query(Evidence).filter(
                    Evidence.id.in_([e[0] for e in self.evidence])).delete(
                    synchronize_session=False)
            # The ingestion route writes provenance rows on its own, so the test
            # never learns their ids: reach them through the parents it does own.
            provenance = []
            if self.assertions:
                provenance.append(ExternalAssertion.id.in_(self.assertions))
            if self.systems:
                provenance.append(
                    ExternalAssertion.external_system_id.in_(self.systems))
            if self.clients:
                provenance.append(ExternalAssertion.api_client_id.in_(self.clients))
            if provenance:
                session.query(ExternalAssertion).filter(or_(*provenance)).delete(
                    synchronize_session=False)
            if self.systems:
                session.query(ExternalReference).filter(
                    ExternalReference.external_system_id.in_(self.systems)).delete(
                    synchronize_session=False)
            if self.clients:
                # idempotency_keys and api_credentials both hang off the client,
                # so they go before it.
                session.query(IdempotencyKey).filter(
                    IdempotencyKey.client_id.in_(self.clients)).delete(
                    synchronize_session=False)
                session.query(ApiCredential).filter(
                    ApiCredential.client_id.in_(self.clients)).delete(
                    synchronize_session=False)
                session.query(ApiClient).filter(
                    ApiClient.id.in_(self.clients)).delete(
                    synchronize_session=False)
            if self.users:
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.user_id.in_(self.users)).delete(
                    synchronize_session=False)
            if self.credentials:
                session.query(ApiCredential).filter(
                    ApiCredential.id.in_(self.credentials)).delete(
                    synchronize_session=False)
            if self.webhooks:
                session.query(WebhookSubscription).filter(
                    WebhookSubscription.id.in_(self.webhooks)).delete(
                    synchronize_session=False)
            if self.references:
                session.query(ExternalReference).filter(
                    ExternalReference.id.in_(self.references)).delete(
                    synchronize_session=False)
            if self.systems:
                session.query(ExternalSystem).filter(
                    ExternalSystem.id.in_(self.systems)).delete(
                    synchronize_session=False)
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
def rows():
    fixture = Fixture()
    yield fixture
    fixture.close()


def make_user(fx: Fixture, label: str) -> str:
    session = get_session()
    try:
        row = User(username=f"ing-{label}-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@ingest.test")
        session.add(row)
        session.commit()
        fx.users.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_org(fx: Fixture, label: str) -> str:
    session = get_session()
    try:
        row = Organization(name=f"Ingest {label} {uuid4().hex[:6]}",
                           code=f"ING-{label}-{uuid4().hex[:8]}", status="ACTIVE")
        session.add(row)
        session.commit()
        fx.orgs.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_project(fx: Fixture, owner_id: str, organization_id: str) -> str:
    session = get_session()
    try:
        row = Project(name=f"ingest {uuid4().hex[:6]}", owner_id=owner_id,
                      organization_id=organization_id)
        session.add(row)
        session.commit()
        fx.projects.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_system(fx: Fixture, organization_id: str) -> str:
    session = get_session()
    try:
        row = ExternalSystem(organization_id=organization_id,
                             name=f"ingest system {uuid4().hex[:6]}",
                             code=f"ing-{uuid4().hex[:12]}",
                             system_type="FIELD_SYSTEM", status="ACTIVE", metadata_={})
        session.add(row)
        session.commit()
        fx.systems.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_client(fx: Fixture, project_id: str | None, scopes: list[str]) -> str:
    session = get_session()
    try:
        row = ApiClient(name=f"ingest-client-{uuid4().hex[:8]}", scopes=scopes,
                        project_id=project_id, status="ACTIVE")
        session.add(row)
        session.commit()
        fx.clients.append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def grant(fx: Fixture, user_id: str, role_name: str, scope_type: str, **scope_ids) -> None:
    session = get_session()
    try:
        auth_service.assign_role(session, user_id=user_id, role_name=role_name,
                                 scope_type=scope_type, **scope_ids)
        session.commit()
        fx.users.append(user_id) if user_id not in fx.users else None
    finally:
        session.close()


def upload_direct(headers: dict | None = None):
    payload = image_bytes()
    response = client.post("/api/v1/evidence",
                           files={"file": ("proof.jpg", payload, "image/jpeg")},
                           headers=headers or {})
    return response, payload


def upload_external(fx: Fixture, headers: dict, *, project_id: str | None = None,
                    system_id: str | None = None, key: str | None = None,
                    payload: bytes | None = None, filename: str = "ext.jpg"):
    payload = payload if payload is not None else image_bytes()
    data = {"external_system_id": system_id or fx.systems[0]}
    if project_id:
        data["project_id"] = project_id
    headers = dict(headers)
    if key:
        headers["Idempotency-Key"] = key
    response = client.post(f"{BASE}/evidence",
                           files={"file": (filename, payload, "image/jpeg")},
                           data=data, headers=headers)
    if response.status_code == 201:
        body = response.json()
        fx.evidence.append((body["evidence_id"], body["storage_key"]))
    return response, payload


def evidence_count_for(project_id: str) -> int:
    session = get_session()
    try:
        return session.query(Evidence).filter(Evidence.project_id == project_id).count()
    finally:
        session.close()


def total_evidence() -> int:
    session = get_session()
    try:
        return session.query(Evidence).count()
    finally:
        session.close()


def ledger_rows(event_type: str, resource_id: str) -> list[AuditLedgerEvent]:
    session = get_session()
    try:
        return (session.query(AuditLedgerEvent)
                .filter(AuditLedgerEvent.event_type == event_type,
                        AuditLedgerEvent.resource_id == resource_id)
                .all())
    finally:
        session.close()


def read_project_id(evidence_id: str) -> str | None:
    session = get_session()
    try:
        row = session.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
        return None if row is None else row.project_id
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 2.2 — the uploader is recorded, from the credential, on every ingestion path
# ---------------------------------------------------------------------------


def test_direct_upload_records_the_caller_as_the_ledger_actor(rows):
    """Before the fix the event existed but carried no actor, so this asserted a
    real row and then named the layer that had lost the identity."""
    owner = make_user(rows, "owner")
    officer = make_user(rows, "officer")
    org = make_org(rows, "alpha")
    project = make_project(rows, owner, org)
    grant(rows, officer, "FIELD_OFFICER", "PROJECT", project_id=project)

    response, _ = upload_direct(user_headers(officer))
    assert response.status_code == 201, response.text
    body = response.json()
    rows.evidence.append((body["evidence_id"], body["storage_key"]))

    events = ledger_rows("EVIDENCE_UPLOADED", body["evidence_id"])
    assert len(events) == 1, "one upload must leave exactly one ledger row"
    assert events[0].actor_id == officer, (
        "the ledger actor is the authenticated principal, not a body field")


def test_external_ingestion_records_the_api_client_that_uploaded(rows):
    """The integration route shares the pipeline, so it shares the attribution."""
    owner = make_user(rows, "owner")
    org = make_org(rows, "alpha")
    project = make_project(rows, owner, org)
    system = make_system(rows, org)
    external = make_client(rows, project, ["external_data.write"])

    response, _ = upload_external(rows, client_headers(external),
                                  project_id=project, system_id=system)
    assert response.status_code == 201, response.text
    events = ledger_rows("EVIDENCE_UPLOADED", response.json()["evidence_id"])
    assert len(events) == 1
    assert events[0].actor_id == external


# ---------------------------------------------------------------------------
# 2.1 — naming a project is a claim, not a grant
# ---------------------------------------------------------------------------


def test_external_evidence_cannot_be_dropped_into_another_project(rows):
    owner = make_user(rows, "owner")
    org_a = make_org(rows, "alpha")
    org_b = make_org(rows, "beta")
    project_a = make_project(rows, owner, org_a)
    project_b = make_project(rows, owner, org_b)
    system = make_system(rows, org_a)
    scoped = make_client(rows, project_a, ["external_data.write"])

    before = total_evidence()
    refused, _ = upload_external(rows, client_headers(scoped),
                                 project_id=project_b, system_id=system)
    assert refused.status_code == 404, refused.text
    assert total_evidence() == before, "a refused ingestion must write no evidence row"

    # Positive control: the same credential, the same permission, its own
    # project — so the refusal above can only be the scope.
    allowed, _ = upload_external(rows, client_headers(scoped),
                                 project_id=project_a, system_id=system)
    assert allowed.status_code == 201, allowed.text
    assert read_project_id(allowed.json()["evidence_id"]) == project_a
    assert evidence_count_for(project_b) == 0


def test_a_project_bound_client_may_not_reach_a_platform_wide_target(rows):
    """A client with a project is not a GLOBAL writer just because it is active."""
    owner = make_user(rows, "owner")
    org = make_org(rows, "alpha")
    project_a = make_project(rows, owner, org)
    project_b = make_project(rows, owner, org)
    system = make_system(rows, org)
    scoped = make_client(rows, project_a, ["external_data.write"])
    platform = make_client(rows, None, ["external_data.write"])

    refused, _ = upload_external(rows, client_headers(scoped),
                                 project_id=project_b, system_id=system)
    assert refused.status_code == 404, refused.text

    allowed, _ = upload_external(rows, client_headers(platform),
                                 project_id=project_b, system_id=system)
    assert allowed.status_code == 201, allowed.text
    assert read_project_id(allowed.json()["evidence_id"]) == project_b


def test_ingestion_without_a_project_needs_no_project_scope(rows):
    """The guard runs only when the caller names a project: an unlinked upload
    stays possible, so the fix did not become a new requirement."""
    owner = make_user(rows, "owner")
    org = make_org(rows, "alpha")
    project = make_project(rows, owner, org)
    system = make_system(rows, org)
    scoped = make_client(rows, project, ["external_data.write"])

    before = total_evidence()
    response, _ = upload_external(rows, client_headers(scoped), system_id=system)
    assert response.status_code == 201, response.text
    assert total_evidence() == before + 1
    assert read_project_id(response.json()["evidence_id"]) is None


# ---------------------------------------------------------------------------
# 2.6 — the advertised Idempotency-Key is honoured, or refused
# ---------------------------------------------------------------------------


def _armed_client(rows):
    owner = make_user(rows, "owner")
    org = make_org(rows, "alpha")
    project = make_project(rows, owner, org)
    system = make_system(rows, org)
    external = make_client(rows, project, ["external_data.write"])
    return project, system, external


def test_retry_with_the_same_key_replays_the_first_result(rows):
    project, system, external = _armed_client(rows)
    payload = image_bytes()
    key = f"idem-{uuid4().hex}"

    first, _ = upload_external(rows, client_headers(external), project_id=project,
                               system_id=system, key=key, payload=payload)
    assert first.status_code == 201, first.text
    after_first = total_evidence()

    second, _ = upload_external(rows, client_headers(external), project_id=project,
                                system_id=system, key=key, payload=payload)
    assert second.status_code == 201, second.text
    assert second.json()["evidence_id"] == first.json()["evidence_id"], (
        "a replay must return the original ingestion, not a new one")
    assert total_evidence() == after_first, (
        "the retry must not create a second evidence row")
    assert len(ledger_rows("EVIDENCE_UPLOADED", first.json()["evidence_id"])) == 1, (
        "and must not append a second audit event for the same evidence")


def test_the_same_key_with_different_bytes_is_a_conflict(rows):
    project, system, external = _armed_client(rows)
    key = f"idem-{uuid4().hex}"

    first, _ = upload_external(rows, client_headers(external), project_id=project,
                               system_id=system, key=key, payload=image_bytes("JPEG"))
    assert first.status_code == 201, first.text
    after_first = total_evidence()

    conflicting, _ = upload_external(rows, client_headers(external), project_id=project,
                                     system_id=system, key=key,
                                     payload=image_bytes("PNG"), filename="other.png")
    assert conflicting.status_code == 409, conflicting.text
    assert total_evidence() == after_first, "a conflict must write nothing"
    assert ledger_rows("EVIDENCE_UPLOADED", first.json()["evidence_id"])[0].actor_id == external


def test_a_key_is_scoped_to_the_client_that_holds_it(rows):
    """Reusing another client's key is a new request, not that client's replay."""
    project, system, first_client = _armed_client(rows)
    second_client = make_client(rows, project, ["external_data.write"])
    payload = image_bytes()
    key = f"idem-{uuid4().hex}"

    first, _ = upload_external(rows, client_headers(first_client), project_id=project,
                               system_id=system, key=key, payload=payload)
    assert first.status_code == 201, first.text

    # Same bytes, same key, different credential: the store is per client, so
    # this is a NEW request and must ingest again rather than replay.
    other, _ = upload_external(rows, client_headers(second_client), project_id=project,
                               system_id=system, key=key, payload=payload)
    assert other.status_code == 201, other.text
    assert other.json()["evidence_id"] != first.json()["evidence_id"]


def test_a_human_caller_is_refused_a_key_it_cannot_store(rows):
    """The key table's client_id is a NOT NULL foreign key to api_clients, so a
    user id could only ever be swallowed by the insert's IntegrityError
    handler. Refusing is honest; pretending to deduplicate is not."""
    owner = make_user(rows, "owner")
    org = make_org(rows, "alpha")
    project = make_project(rows, owner, org)
    system = make_system(rows, org)
    grant(rows, owner, "ADMINISTRATOR", "PROJECT", project_id=project)

    before = total_evidence()
    refused, _ = upload_external(rows, user_headers(owner), project_id=project,
                                 system_id=system, key=f"idem-{uuid4().hex}")
    assert refused.status_code == 400, refused.text
    assert "API-client" in refused.json()["detail"]
    assert total_evidence() == before, "the refusal happens before any ingestion"

    # The same human, without the header, is a working external_data.write
    # holder: the 400 above is the key, not the permission.
    allowed, _ = upload_external(rows, user_headers(owner), project_id=project,
                                 system_id=system)
    assert allowed.status_code == 201, allowed.text
    assert total_evidence() == before + 1
