"""BE-026 integration tests: field operations and offline evidence capture.

Runs against the isolated ``TEST_DATABASE_URL`` with live Postgres/PostGIS,
Redis and MinIO over real HTTP through TestClient (BE-023 bootstrap). Covers
the Stage B §17 matrix: assignment lifecycle and containment, the assigned-work
feed, session lifecycle, idempotent synchronization (including concurrency and
retry-after-timeout), reuse of the existing ingestion validator and fingerprint
pipeline, the conflict taxonomy, the enforce-mode role matrix, and the audit
obligations with chain verification.

Nothing here deletes or updates an audit ledger row: the ledger keeps every
decision this suite makes.
"""

import json
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    Activity,
    ApiClient,
    AuditLedgerEvent,
    Claim,
    Evidence,
    EvidenceMetadata,
    FieldAssignment,
    FieldCaptureOperation,
    FieldSession,
    Organization,
    OrganizationalUnit,
    Project,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_session
from backend.services import audit_ledger as audit_service
from backend.services import authorization as auth_service
from backend.services import field_operations as field_service
from backend.services.fingerprinting import process_evidence
from backend.services.storage import StorageService

client = TestClient(app)

FIELD_EVENT_TYPES = (
    "FIELD_ASSIGNMENT_CREATED",
    "FIELD_ASSIGNMENT_STATUS_CHANGED",
    "FIELD_ASSIGNMENT_EXPIRED",
    "FIELD_ASSIGNMENT_ACCESSED",
    "FIELD_ASSIGNMENT_SECURITY_FAILURE",
    "FIELD_SESSION_OPENED",
    "FIELD_SESSION_CLOSED",
    "FIELD_SYNC_ACCEPTED",
    "FIELD_SYNC_DUPLICATE",
    "FIELD_SYNC_REJECTED",
    "FIELD_SYNC_CONFLICT",
    "FIELD_SYNC_CONFLICT_RESOLVED",
    "FIELD_EVIDENCE_ASSOCIATED",
)


# ---------------------------------------------------------------------------
# fixtures and helpers
# ---------------------------------------------------------------------------

def headers_for(principal_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{principal_id}"}


def client_headers(client_id: str) -> dict:
    return {"Authorization": f"Bearer dev-client-{client_id}"}


def now_iso(minutes_offset: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes_offset)).isoformat()


def op_id() -> str:
    return f"op-{uuid4().hex[:16]}"


@contextmanager
def enforcing():
    """Run with AUTH_MODE=enforcing so no anonymous bypass exists anywhere."""
    original = settings.auth_mode
    settings.auth_mode = "enforcing"
    try:
        yield
    finally:
        settings.auth_mode = original


@pytest.fixture(autouse=True)
def seed_catalogue():
    session = get_session()
    try:
        auth_service.ensure_default_catalogue(session)
    finally:
        session.close()


def make_user(label: str) -> User:
    session = get_session()
    try:
        user = User(username=f"be026-{label}-{uuid4().hex[:8]}",
                    email=f"{uuid4().hex[:8]}@example.com")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()


def grant(user_id: str, role: str, scope: str, scope_id: str | None = None) -> None:
    session = get_session()
    try:
        kwargs: dict = {}
        if scope == "ORGANIZATION":
            kwargs["organization_id"] = scope_id
        elif scope == "ORGANIZATIONAL_UNIT":
            kwargs["organizational_unit_id"] = scope_id
        elif scope == "PROJECT":
            kwargs["project_id"] = scope_id
        auth_service.assign_role(
            session, user_id=user_id, role_name=role, scope_type=scope, **kwargs)
        session.commit()
    finally:
        session.close()


def create_org(label: str) -> Organization:
    session = get_session()
    try:
        org = auth_service.create_organization(
            session, name=f"Org {label}", code=f"be026-{label}-{uuid4().hex[:8]}")
        session.commit()
        session.refresh(org)
        session.expunge(org)
        return org
    finally:
        session.close()


def create_unit(org_id: str, label: str) -> OrganizationalUnit:
    session = get_session()
    try:
        unit = auth_service.create_organizational_unit(
            session, organization_id=org_id, name=f"Unit {label}",
            code=f"be026-{label}-{uuid4().hex[:8]}")
        session.commit()
        session.refresh(unit)
        session.expunge(unit)
        return unit
    finally:
        session.close()


def make_project(owner_id: str, name: str, *, org_id: str | None = None,
                 unit_id: str | None = None) -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": owner_id})
    assert response.status_code == 201
    project_id = response.json()["id"]
    if org_id or unit_id:
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
    return response.json()


def make_claim(project_id: str, claimant_id: str) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={"claimant_id": claimant_id, "title": f"claim {uuid4().hex[:6]}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def make_activity(project_id: str, actor_id: str) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/activities",
        json={"actor_id": actor_id, "verb": "observed"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def new_assignment(*, user_id, project_id, claim_id=None, activity_id=None,
                   expires_at=None, valid_from=None, instructions=None,
                   actor_id=None) -> dict:
    body = {
        "user_id": user_id,
        "project_id": project_id,
        "claim_id": claim_id,
        "activity_id": activity_id,
        "expires_at": expires_at,
        "valid_from": valid_from,
        "instructions": instructions,
    }
    response = client.post(
        "/api/v1/field/assignments",
        json={key: value for key, value in body.items() if value is not None},
        headers=headers_for(actor_id) if actor_id else None,
    )
    assert response.status_code == 201, response.text
    return response.json()


def open_session(user_id: str, assignment_id: str, **kwargs):
    body = {"assignment_id": assignment_id, **kwargs}
    return client.post("/api/v1/field/sessions", json=body, headers=headers_for(user_id))


def jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=(20, 120, 220)).save(output, format="JPEG")
    return output.getvalue()


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(200, 30, 30)).save(output, format="PNG")
    return output.getvalue()


def sync(user_id: str, operation_id: str, *, data: bytes | None = None,
         content_type: str = "image/jpeg", filename: str = "capture.jpg",
         extra_fields: dict | None = None, auth: dict | None = None, **fields):
    form = {"client_operation_id": operation_id}
    form.update({key: value for key, value in fields.items() if value is not None})
    form.update(extra_fields or {})
    return client.post(
        "/api/v1/field/sync",
        headers=auth if auth is not None else headers_for(user_id),
        files={"file": (filename, data if data is not None else jpeg_bytes(), content_type)},
        data=form,
    )


def rows(model, **filters) -> list:
    session = get_session()
    try:
        query = session.query(model)
        for key, value in filters.items():
            query = query.filter(getattr(model, key) == value)
        found = query.all()
        session.expunge_all()
        return found
    finally:
        session.close()


def count(model, **filters) -> int:
    session = get_session()
    try:
        query = session.query(model)
        for key, value in filters.items():
            query = query.filter(getattr(model, key) == value)
        return query.count()
    finally:
        session.close()


def events(event_type: str, *, resource_id: str | None = None,
           project_id: str | None = None) -> list[dict]:
    session = get_session()
    try:
        query = session.query(AuditLedgerEvent).filter(
            AuditLedgerEvent.event_type == event_type)
        if resource_id:
            query = query.filter(AuditLedgerEvent.resource_id == resource_id)
        if project_id:
            query = query.filter(AuditLedgerEvent.project_id == project_id)
        out = query.order_by(AuditLedgerEvent.sequence_number).all()
        return [
            {
                "sequence_number": row.sequence_number,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "actor_id": row.actor_id,
                "project_id": row.project_id,
                "payload": row.payload,
            }
            for row in out
        ]
    finally:
        session.close()


class Harness:
    """One scenario's objects, with FK-safe teardown.

    Audit ledger rows are deliberately never touched: they are the record of
    the run, and the BE-023 guard forbids removing them.
    """

    def __init__(self):
        self.user_ids: list[str] = []
        self.project_ids: list[str] = []
        self.org_ids: list[str] = []
        self.unit_ids: list[str] = []
        self.claim_ids: list[str] = []
        self.activity_ids: list[str] = []
        self.evidence_ids: list[str] = []
        self.client_ids: list[str] = []

    def user(self, label: str) -> User:
        user = make_user(label)
        self.user_ids.append(str(user.id))
        return user

    def org(self, label: str) -> Organization:
        org = create_org(label)
        self.org_ids.append(str(org.id))
        return org

    def unit(self, org_id: str, label: str) -> OrganizationalUnit:
        unit = create_unit(org_id, label)
        self.unit_ids.append(str(unit.id))
        return unit

    def project(self, owner_id: str, label: str, **scope) -> dict:
        project = make_project(owner_id, f"be026 {label} {uuid4().hex[:6]}", **scope)
        self.project_ids.append(project["id"])
        return project

    def claim(self, project_id: str, claimant_id: str) -> str:
        claim_id = make_claim(project_id, claimant_id)
        self.claim_ids.append(claim_id)
        return claim_id

    def activity(self, project_id: str, actor_id: str) -> str:
        activity_id = make_activity(project_id, actor_id)
        self.activity_ids.append(activity_id)
        return activity_id

    def track_evidence(self, evidence_id: str) -> str:
        self.evidence_ids.append(evidence_id)
        return evidence_id

    def track_client(self, client_id: str) -> str:
        self.client_ids.append(client_id)
        return client_id

    def close(self) -> None:
        session = get_session()
        try:
            if self.evidence_ids:
                session.query(EvidenceMetadata).filter(
                    EvidenceMetadata.evidence_id.in_(self.evidence_ids)).delete(
                    synchronize_session=False)
                session.query(Evidence).filter(
                    Evidence.id.in_(self.evidence_ids)).delete(synchronize_session=False)
            owner_filters = [("user_id", self.user_ids), ("project_id", self.project_ids)]
            for column, values in owner_filters:
                if values:
                    session.query(FieldCaptureOperation).filter(
                        getattr(FieldCaptureOperation, column).in_(values)).delete(
                        synchronize_session=False)
            if self.user_ids:
                session.query(FieldSession).filter(
                    FieldSession.user_id.in_(self.user_ids)).delete(
                    synchronize_session=False)
                session.query(FieldAssignment).filter(
                    FieldAssignment.user_id.in_(self.user_ids)).delete(
                    synchronize_session=False)
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.user_id.in_(self.user_ids)).delete(
                    synchronize_session=False)
            # Claims and activities reference projects with RESTRICT keys, so
            # they leave before the project does.
            if self.activity_ids:
                session.query(Activity).filter(
                    Activity.id.in_(self.activity_ids)).delete(synchronize_session=False)
            if self.claim_ids:
                session.query(Claim).filter(Claim.id.in_(self.claim_ids)).delete(
                    synchronize_session=False)
            if self.project_ids:
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.project_id.in_(self.project_ids)).delete(
                    synchronize_session=False)
                session.query(Project).filter(
                    Project.id.in_(self.project_ids)).delete(synchronize_session=False)
            if self.user_ids:
                session.query(User).filter(User.id.in_(self.user_ids)).delete(
                    synchronize_session=False)
            if self.unit_ids:
                session.query(OrganizationalUnit).filter(
                    OrganizationalUnit.id.in_(self.unit_ids)).delete(
                    synchronize_session=False)
            if self.org_ids:
                session.query(Organization).filter(
                    Organization.id.in_(self.org_ids)).delete(synchronize_session=False)
            if self.client_ids:
                session.query(ApiClient).filter(
                    ApiClient.id.in_(self.client_ids)).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()
        storage = StorageService()
        for evidence_id in self.evidence_ids:
            storage.delete_object(storage.quarantine_bucket,
                                  f"quarantine/{evidence_id}/original")


@pytest.fixture
def harness():
    world = Harness()
    try:
        yield world
    finally:
        world.close()


def officer_world(harness, label: str = "field"):
    """Org + project + officer granted FIELD_OFFICER for that project."""
    admin = harness.user(f"{label}-admin")
    grant(str(admin.id), "ADMINISTRATOR", "GLOBAL")
    org = harness.org(label)
    project = harness.project(str(admin.id), label, org_id=str(org.id))
    officer = harness.user(f"{label}-officer")
    grant(str(officer.id), "FIELD_OFFICER", "ORGANIZATION", str(org.id))
    return admin, org, project, officer


# ---------------------------------------------------------------------------
# assignment lifecycle
# ---------------------------------------------------------------------------

def test_assignment_creation_derives_scope_and_never_accepts_it(harness):
    admin, org, project, officer = officer_world(harness, "derive")
    claim_id = harness.claim(project["id"], str(officer.id))
    activity_id = harness.activity(project["id"], str(officer.id))

    created = client.post(
        "/api/v1/field/assignments",
        json={
            "user_id": str(officer.id),
            "project_id": project["id"],
            "claim_id": claim_id,
            "activity_id": activity_id,
            "instructions": "Photograph the culvert",
        },
        headers=headers_for(str(admin.id)),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "ACTIVE"
    assert body["organization_id"] == str(org.id)
    assert body["claim_id"] == claim_id
    assert body["activity_id"] == activity_id

    # No client-supplied organizational field exists to forge.
    forged = client.post(
        "/api/v1/field/assignments",
        json={
            "user_id": str(officer.id),
            "project_id": project["id"],
            "organization_id": str(org.id),
        },
        headers=headers_for(str(admin.id)),
    )
    assert forged.status_code == 422

    # Two partial unique indexes govern ACTIVE work: one per
    # (officer, project, claim) and one per (officer, project) for claim-less
    # assignments. Re-using the same claim is the conflict; a claim-less round
    # alongside claim-specific work is legitimate, and is exactly what makes an
    # unbound capture ambiguous later.
    duplicate = client.post(
        "/api/v1/field/assignments",
        json={"user_id": str(officer.id), "project_id": project["id"],
              "claim_id": claim_id},
        headers=headers_for(str(admin.id)),
    )
    assert duplicate.status_code == 409, duplicate.text
    assert count(FieldAssignment, project_id=project["id"], claim_id=claim_id) == 1

    general = client.post(
        "/api/v1/field/assignments",
        json={"user_id": str(officer.id), "project_id": project["id"]},
        headers=headers_for(str(admin.id)),
    )
    assert general.status_code == 201, general.text
    assert general.json()["claim_id"] is None

    second_general = client.post(
        "/api/v1/field/assignments",
        json={"user_id": str(officer.id), "project_id": project["id"]},
        headers=headers_for(str(admin.id)),
    )
    assert second_general.status_code == 409


def test_assignment_rejects_context_from_another_project(harness):
    admin, org, project, officer = officer_world(harness, "ctx")
    other_admin = harness.user("ctx-other-admin")
    grant(str(other_admin.id), "ADMINISTRATOR", "GLOBAL")
    other = harness.project(str(other_admin.id), "other", org_id=str(org.id))
    foreign_claim = harness.claim(other["id"], str(officer.id))

    rejected = client.post(
        "/api/v1/field/assignments",
        json={
            "user_id": str(officer.id),
            "project_id": project["id"],
            "claim_id": foreign_claim,
        },
        headers=headers_for(str(admin.id)),
    )
    assert rejected.status_code == 422
    assert "claim_id must reference a claim in this project" in rejected.json()["detail"]
    assert count(FieldAssignment, project_id=project["id"]) == 0

    same_project_claim = harness.claim(project["id"], str(officer.id))
    accepted = client.post(
        "/api/v1/field/assignments",
        json={"user_id": str(officer.id), "project_id": project["id"],
              "claim_id": same_project_claim},
        headers=headers_for(str(admin.id)),
    )
    assert accepted.status_code == 201, accepted.text


def test_assignment_pagination_is_bounded_and_scoped(harness):
    admin, org, project, officer = officer_world(harness, "page")
    second = harness.project(str(admin.id), "page2", org_id=str(org.id))
    for target in (project, second):
        created = new_assignment(user_id=str(officer.id), project_id=target["id"])
        assert created["status"] == "ACTIVE"
    other_officer = harness.user("page-other")
    grant(str(other_officer.id), "FIELD_OFFICER", "ORGANIZATION", str(org.id))
    new_assignment(user_id=str(other_officer.id), project_id=project["id"])

    # A GLOBAL administrator's listing spans the whole database, so the stable
    # expectation is per-project: this scenario owns exactly two assignments
    # here (the officer's and the colleague's).
    scoped = {"project_id": project["id"]}
    listed = client.get("/api/v1/field/assignments",
                        params={**scoped, "limit": 1, "offset": 0},
                        headers=headers_for(str(admin.id)))
    assert listed.status_code == 200
    page_one = listed.json()
    assert page_one["total"] == 2
    assert len(page_one["items"]) == 1

    offset_page = client.get("/api/v1/field/assignments",
                             params={**scoped, "limit": 1, "offset": 1},
                             headers=headers_for(str(admin.id))).json()
    assert offset_page["items"][0]["id"] != page_one["items"][0]["id"]

    by_user = client.get("/api/v1/field/assignments",
                         params={"user_id": str(officer.id)},
                         headers=headers_for(str(admin.id))).json()
    assert by_user["total"] == 2

    # Out-of-range bounds are validation failures, never silent clamping.
    assert client.get("/api/v1/field/assignments", params={"limit": 0},
                      headers=headers_for(str(admin.id))).status_code == 422
    assert client.get("/api/v1/field/assignments", params={"limit": 101},
                      headers=headers_for(str(admin.id))).status_code == 422


def test_cross_organization_assignment_denial(harness):
    admin_a, org_a, project_a, officer_a = officer_world(harness, "orgA")
    org_b = harness.org("orgB")
    project_b = harness.project(str(admin_a.id), "orgBproj", org_id=str(org_b.id))

    with enforcing():
        org_a_admin = harness.user("orgA-admin")
        grant(str(org_a_admin.id), "ADMINISTRATOR", "ORGANIZATION", str(org_a.id))
        headers = headers_for(str(org_a_admin.id))

        # Creating work inside the caller's own organization succeeds.
        assert client.post(
            "/api/v1/field/assignments",
            json={"user_id": str(officer_a.id), "project_id": project_a["id"]},
            headers=headers,
        ).status_code == 201

        # A foreign organization is indistinguishable from absent.
        foreign_create = client.post(
            "/api/v1/field/assignments",
            json={"user_id": str(officer_a.id), "project_id": project_b["id"]},
            headers=headers,
        )
        assert foreign_create.status_code == 404

        # Listing cannot enumerate, or even count, another organization's work.
        listed = client.get("/api/v1/field/assignments", headers=headers).json()
        assert all(item["project_id"] == project_a["id"] for item in listed["items"])
        assert listed["total"] == 1

        foreign_project_filter = client.get(
            "/api/v1/field/assignments",
            params={"project_id": project_b["id"]},
            headers=headers,
        )
        assert foreign_project_filter.status_code == 404


def test_scope_denied_session_open_is_audited_as_a_security_failure(harness):
    """F-SE-05 (Stage E): an assignment is never authority, and the refusal is recorded.

    The officer *owns* this assignment, so ownership passes and it is the
    project scope gate that refuses. Task §16 lists assignment-related security
    failures among the minimum audit coverage, and the synchronization route
    already audits that same gate; a session-open denial must not be silent.
    """
    admin, _org_a, _project_a, officer = officer_world(harness, "xorgaudit")
    org_b = harness.org("xorgaudit-b")
    project_b = harness.project(str(admin.id), "xorgaudit-bproj", org_id=str(org_b.id))
    foreign = new_assignment(user_id=str(officer.id), project_id=project_b["id"])

    refused = open_session(str(officer.id), foreign["id"], client_device_id="pixel-7")
    assert refused.status_code == 404, refused.text
    assert refused.json()["detail"]["sync_status"] == "authorization_denied"
    assert count(FieldSession, assignment_id=foreign["id"]) == 0

    recorded = [row for row in events("FIELD_ASSIGNMENT_SECURITY_FAILURE")
                if row["payload"].get("failure") == "SCOPE_GATE_DENIED"
                and str(row["payload"].get("assignment_id")) == foreign["id"]]
    assert recorded, "a scope-denied session-open left no security failure behind"
    assert recorded[-1]["actor_id"] == str(officer.id)
    payload = recorded[-1]["payload"]
    assert payload["project_id"] == project_b["id"]
    assert payload["status"] == "authorization_denied"


def test_assignment_release_and_revocation_are_terminal(harness):
    admin, org, project, officer = officer_world(harness, "close")
    assignment = new_assignment(user_id=str(officer.id), project_id=project["id"])

    released = client.patch(
        f"/api/v1/field/assignments/{assignment['id']}/status",
        json={"status": "RELEASED", "reason": "work complete"},
        headers=headers_for(str(admin.id)),
    )
    assert released.status_code == 200
    assert released.json()["status"] == "RELEASED"
    assert released.json()["closed_reason"] == "work complete"

    again = client.patch(
        f"/api/v1/field/assignments/{assignment['id']}/status",
        json={"status": "REVOKED", "reason": "twice"},
        headers=headers_for(str(admin.id)),
    )
    assert again.status_code == 409

    # EXPIRED is server-set, never requestable.
    assert client.patch(
        f"/api/v1/field/assignments/{assignment['id']}/status",
        json={"status": "EXPIRED", "reason": "no"},
        headers=headers_for(str(admin.id)),
    ).status_code == 422

    changed = events("FIELD_ASSIGNMENT_STATUS_CHANGED", resource_id=assignment["id"])
    assert changed[-1]["payload"]["before_status"] == "ACTIVE"
    assert changed[-1]["payload"]["after_status"] == "RELEASED"
    assert changed[-1]["actor_id"] == str(admin.id)


def test_assignment_expiration_is_lazy_server_set_and_audited(harness):
    admin, org, project, officer = officer_world(harness, "expire")
    assignment = new_assignment(
        user_id=str(officer.id),
        project_id=project["id"],
        expires_at=now_iso(-5),
    )
    # Still ACTIVE in the table until something touches it.
    assert rows(FieldAssignment, id=assignment["id"])[0].status == "ACTIVE"

    feed = client.get("/api/v1/field/work", headers=headers_for(str(officer.id)))
    assert feed.status_code == 200
    assert feed.json()["total"] == 0
    assert rows(FieldAssignment, id=assignment["id"])[0].status == "EXPIRED"
    assert events("FIELD_ASSIGNMENT_EXPIRED", resource_id=assignment["id"])


# ---------------------------------------------------------------------------
# assigned-work feed and sessions
# ---------------------------------------------------------------------------

def test_work_feed_exposes_only_the_callers_active_assignments(harness):
    admin, org, project, officer = officer_world(harness, "feed")
    claim_id = harness.claim(project["id"], str(officer.id))
    mine = new_assignment(user_id=str(officer.id), project_id=project["id"],
                          claim_id=claim_id)
    colleague = harness.user("feed-colleague")
    grant(str(colleague.id), "FIELD_OFFICER", "ORGANIZATION", str(org.id))
    theirs = new_assignment(user_id=str(colleague.id), project_id=project["id"])

    feed = client.get("/api/v1/field/work", headers=headers_for(str(officer.id)))
    assert feed.status_code == 200
    body = feed.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["assignment_id"] == mine["id"]
    assert item["claim"]["id"] == claim_id
    assert item["project"]["id"] == project["id"]
    # Data minimization: only the assignment's own context, nothing else.
    assert set(item.keys()) == {
        "assignment_id", "status", "project", "organization_id", "valid_from",
        "expires_at", "instructions", "active_session_id", "claim", "activity",
    }
    assert all(entry["assignment_id"] != theirs["id"] for entry in body["items"])

    # Polling the feed is not a ledger event (Stage B §10 soft deviation).
    before = count(AuditLedgerEvent)
    client.get("/api/v1/field/work", headers=headers_for(str(officer.id)))
    assert count(AuditLedgerEvent) == before


def test_session_open_requires_ownership_and_current_authority(harness):
    admin, org, project, officer = officer_world(harness, "sess")
    assignment = new_assignment(user_id=str(officer.id), project_id=project["id"])
    stranger = harness.user("sess-stranger")
    grant(str(stranger.id), "FIELD_OFFICER", "ORGANIZATION", str(org.id))

    foreign = open_session(str(stranger.id), assignment["id"])
    assert foreign.status_code == 404
    assert foreign.json()["detail"]["sync_status"] == "authorization_denied"
    security = events("FIELD_ASSIGNMENT_SECURITY_FAILURE")
    assert security[-1]["payload"]["failure"] == "FOREIGN_OR_MISSING_ASSIGNMENT"
    assert count(FieldSession, assignment_id=assignment["id"]) == 0

    opened = open_session(str(officer.id), assignment["id"],
                          session_label="morning sweep", client_device_id="pixel-7")
    assert opened.status_code == 201, opened.text
    assert opened.json()["status"] == "ACTIVE"
    assert opened.json()["project_id"] == project["id"]
    assert events("FIELD_SESSION_OPENED", resource_id=opened.json()["id"])

    # One open session per (assignment, device).
    repeat = open_session(str(officer.id), assignment["id"], client_device_id="pixel-7")
    assert repeat.status_code == 409

    # A second device is a second session, not a replacement.
    second_device = open_session(str(officer.id), assignment["id"],
                                 client_device_id="pixel-8")
    assert second_device.status_code == 201
    assert second_device.json()["id"] != opened.json()["id"]


def test_session_close_is_owner_only_and_guarded(harness):
    admin, org, project, officer = officer_world(harness, "close-sess")
    assignment = new_assignment(user_id=str(officer.id), project_id=project["id"])
    session_id = open_session(str(officer.id), assignment["id"]).json()["id"]

    closed = client.post(f"/api/v1/field/sessions/{session_id}/close",
                         json={"reason": "end of shift"},
                         headers=headers_for(str(officer.id)))
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["close_reason"] == "end of shift"
    assert client.post(f"/api/v1/field/sessions/{session_id}/close",
                       json={"reason": "again"},
                       headers=headers_for(str(officer.id))).status_code == 409
    assert events("FIELD_SESSION_CLOSED", resource_id=session_id)


def test_session_close_by_another_officer_is_not_found(harness):
    admin, org, project, officer = officer_world(harness, "close-for")
    assignment = new_assignment(user_id=str(officer.id), project_id=project["id"])
    session_id = open_session(str(officer.id), assignment["id"]).json()["id"]

    colleague = harness.user("close-for-colleague")
    grant(str(colleague.id), "FIELD_OFFICER", "ORGANIZATION", str(org.id))
    hijack = client.post(f"/api/v1/field/sessions/{session_id}/close",
                         json={"reason": "not mine"},
                         headers=headers_for(str(colleague.id)))
    assert hijack.status_code == 404
    assert rows(FieldSession, id=session_id)[0].status == "ACTIVE"


# ---------------------------------------------------------------------------
# synchronization: happy path, idempotency, concurrency
# ---------------------------------------------------------------------------

def prepared(harness, label: str):
    """Officer with an active assignment, claim and an open session."""
    admin, org, project, officer = officer_world(harness, label)
    claim_id = harness.claim(project["id"], str(officer.id))
    assignment = new_assignment(user_id=str(officer.id), project_id=project["id"],
                                claim_id=claim_id)
    session = open_session(str(officer.id), assignment["id"],
                           client_device_id="pixel-7").json()
    return admin, org, project, officer, assignment, session, claim_id


def test_first_sync_accepts_and_associates_through_the_existing_pipeline(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "accept")
    payload = jpeg_bytes()
    captured, queued = now_iso(-120), now_iso(-118)

    response = sync(
        str(officer.id), op_id(),
        data=payload,
        session_id=session["id"],
        captured_at=captured,
        queued_at=queued,
        uploaded_at=now_iso(-3),
        latitude="53.3498",
        longitude="-6.2603",
        capture_accuracy_m="8.50",
        altitude_m="54.0",
        location_source="DEVICE_GPS",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["sync_status"] == "accepted"
    assert body["status"] == "ACCEPTED"
    assert body["evidence_id"]
    assert body["evidence_status"] == "uploaded_quarantine"
    assert body["project_id"] == project["id"]
    assert body["claim_id"] == claim_id
    assert body["assignment_id"] == assignment["id"]
    assert body["location"]["reported"] is True
    assert body["file_size"] == len(payload)
    # Client-asserted and server-observed time stay separate, unmodified.
    assert body["captured_at"].startswith(captured[:19])
    assert body["queued_at"].startswith(queued[:19])
    assert body["received_at"] and body["processed_at"]

    operation = rows(FieldCaptureOperation, id=body["operation_id"])[0]
    evidence = rows(Evidence, id=body["evidence_id"])[0]
    assert evidence.project_id == project["id"]
    assert evidence.claim_id == claim_id
    assert evidence.status == "uploaded_quarantine"
    assert evidence.storage_key == f"quarantine/{body['evidence_id']}/original"
    harness.track_evidence(body["evidence_id"])
    storage = StorageService()
    assert storage.object_exists(storage.quarantine_bucket, evidence.storage_key)

    session_db = get_session()
    try:
        point = session_db.execute(
            text("SELECT ST_AsText(location), ST_SRID(location) FROM evidence "
                 "WHERE id=:i"),
            {"i": body["evidence_id"]},
        ).one()
    finally:
        session_db.close()
    assert point[0] == "POINT(-6.2603 53.3498)"
    assert point[1] == 4326

    accepted = events("FIELD_SYNC_ACCEPTED", resource_id=body["operation_id"])[-1]
    assert accepted["actor_id"] == str(officer.id)
    assert accepted["project_id"] == project["id"]
    associated = events("FIELD_EVIDENCE_ASSOCIATED", resource_id=body["evidence_id"])[-1]
    assert associated["payload"]["claim_id"] == claim_id


def test_exact_duplicate_sync_is_already_synchronized_with_one_evidence_row(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "dup")
    payload = jpeg_bytes()
    operation_id = op_id()
    fields = dict(session_id=session["id"], captured_at=now_iso(-60),
                  latitude="53.3498", longitude="-6.2603", location_source="DEVICE_GPS")

    first = sync(str(officer.id), operation_id, data=payload, **fields)
    assert first.status_code == 201
    evidence_id = first.json()["evidence_id"]
    harness.track_evidence(evidence_id)

    retry = sync(str(officer.id), operation_id, data=payload, **fields)
    assert retry.status_code == 200
    assert retry.json()["sync_status"] == "already_synchronized"
    assert retry.json()["evidence_id"] == evidence_id
    assert retry.json()["sync_count"] == 2

    assert count(Evidence, id=evidence_id) == 1
    assert count(FieldCaptureOperation, client_operation_id=operation_id) == 1
    duplicate = events("FIELD_SYNC_DUPLICATE", resource_id=retry.json()["operation_id"])[-1]
    assert duplicate["payload"]["sync_count"] == 2
    assert duplicate["payload"]["evidence_id"] == evidence_id

    third = sync(str(officer.id), operation_id, data=payload, **fields)
    assert third.json()["sync_status"] == "already_synchronized"
    assert count(FieldCaptureOperation, client_operation_id=operation_id) == 1


def test_same_operation_identity_with_different_payload_conflicts(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "mismatch")
    payload = jpeg_bytes()
    operation_id = op_id()

    first = sync(str(officer.id), operation_id, data=payload,
                 session_id=session["id"], latitude="53.3498", longitude="-6.2603",
                 location_source="DEVICE_GPS")
    assert first.status_code == 201
    evidence_id = first.json()["evidence_id"]
    harness.track_evidence(evidence_id)
    stored = rows(FieldCaptureOperation, id=first.json()["operation_id"])[0]

    different_bytes = sync(str(officer.id), operation_id, data=png_bytes(),
                           session_id=session["id"], latitude="53.3498",
                           longitude="-6.2603", location_source="DEVICE_GPS")
    assert different_bytes.status_code == 409
    # A decided outcome is a FieldSyncResponse body, not an error envelope.
    body = different_bytes.json()
    assert body["sync_status"] == "conflict"
    assert body["conflict_reason"] == "PAYLOAD_MISMATCH"
    assert body["message"].startswith("client_operation_id was already used")

    # Nothing was overwritten and nothing new was ingested.
    after = rows(FieldCaptureOperation, id=stored.id)[0]
    assert after.status == "ACCEPTED"
    assert after.request_hash == stored.request_hash
    assert after.evidence_id == evidence_id
    assert count(Evidence, id=evidence_id) == 1
    conflict = events("FIELD_SYNC_CONFLICT", resource_id=stored.id)[-1]
    assert conflict["payload"]["conflict_reason"] == "PAYLOAD_MISMATCH"
    assert conflict["payload"]["stored_request_hash"] == stored.request_hash

    # Same identity, different metadata only, also conflicts.
    different_metadata = sync(str(officer.id), operation_id, data=payload,
                              session_id=session["id"], latitude="12.25",
                              longitude="-6.2603", location_source="DEVICE_GPS")
    assert different_metadata.status_code == 409


def test_retry_after_timeout_recovers_the_stored_outcome(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "retry")
    payload = jpeg_bytes()
    operation_id = op_id()
    accepted = sync(str(officer.id), operation_id, data=payload,
                    session_id=session["id"])
    evidence_id = harness.track_evidence(accepted.json()["evidence_id"])

    recovered = client.get(f"/api/v1/field/captures/{operation_id}",
                           headers=headers_for(str(officer.id)))
    assert recovered.status_code == 200
    body = recovered.json()
    assert body["status"] == "ACCEPTED"
    assert body["evidence_id"] == evidence_id
    stored = rows(FieldCaptureOperation, id=body["id"])[0]
    assert stored.request_hash == body["request_hash"]

    # Another officer's identifier is indistinguishable from a missing one.
    stranger = harness.user("retry-stranger")
    grant(str(stranger.id), "FIELD_OFFICER", "GLOBAL")
    assert client.get(f"/api/v1/field/captures/{operation_id}",
                      headers=headers_for(str(stranger.id))).status_code == 404
    assert client.get("/api/v1/field/captures/short",
                      headers=headers_for(str(officer.id))).status_code == 422
    assert client.get(f"/api/v1/field/captures/op-{uuid4().hex[:16]}",
                      headers=headers_for(str(officer.id))).status_code == 404


def test_concurrent_first_submissions_create_exactly_one_accepted_capture(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "race")
    payload = jpeg_bytes()
    operation_id = op_id()
    results: list[int] = []
    barrier = threading.Barrier(5)

    def submit():
        barrier.wait()
        response = sync(str(officer.id), operation_id, data=payload,
                        session_id=session["id"], latitude="53.3498",
                        longitude="-6.2603", location_source="DEVICE_GPS")
        results.append(response.status_code)

    threads = [threading.Thread(target=submit) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert len(results) == 5
    assert results.count(201) == 1, results
    assert set(results) <= {200, 201, 409, 503}, results
    operations = rows(FieldCaptureOperation, client_operation_id=operation_id)
    assert len(operations) == 1
    assert operations[0].status == "ACCEPTED"
    harness.track_evidence(str(operations[0].evidence_id))
    assert count(Evidence, id=operations[0].evidence_id) == 1


def test_abandoned_reservation_is_adopted_and_lands_exactly_once(harness):
    """The crash-between-reservation-and-ingest recovery path."""
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "stale")
    payload = jpeg_bytes()
    operation_id = op_id()
    fields = dict(session_id=session["id"], latitude="53.3498", longitude="-6.2603",
                  location_source="DEVICE_GPS", captured_at=now_iso(-400))
    principal_db = get_session()
    try:
        principal = auth_service.resolve_user_principal(principal_db, str(officer.id))
    finally:
        principal_db.close()
    request = field_service.build_sync_request(
        principal=principal,
        data=payload, filename="capture.jpg", declared_content_type="image/jpeg",
        client_operation_id=operation_id, **fields,
    )
    session_db = get_session()
    try:
        session_db.execute(
            text(
                "INSERT INTO field_capture_operations ("
                " id, user_id, client_operation_id, session_id, assignment_id,"
                " project_id, claim_id, request_hash, payload_sha256, filename,"
                " declared_content_type, file_size, status, captured_at, received_at)"
                " VALUES (:id, :user_id, :op, :session_id, :assignment_id,"
                " :project_id, :claim_id, :request_hash, :payload_sha256,"
                " :filename, :declared_content_type, :file_size, 'PENDING',"
                " :captured_at, :received_at)"
            ),
            {
                "id": str(uuid4()),
                "user_id": str(officer.id),
                "op": operation_id,
                "session_id": session["id"],
                "assignment_id": assignment["id"],
                "project_id": project["id"],
                "claim_id": claim_id,
                "request_hash": request.request_hash,
                "payload_sha256": request.payload_sha256,
                "filename": "capture.jpg",
                "declared_content_type": "image/jpeg",
                "file_size": len(payload),
                "captured_at": request.captured_at,
                "received_at": datetime.now(timezone.utc)
                - timedelta(seconds=field_service.STALE_PENDING_SECONDS + 60),
            },
        )
        session_db.commit()
    finally:
        session_db.close()

    in_flight = sync(str(officer.id), operation_id, data=payload, **fields)
    assert in_flight.status_code == 201, in_flight.text
    assert in_flight.json()["sync_status"] == "accepted"
    evidence_id = harness.track_evidence(in_flight.json()["evidence_id"])
    assert count(FieldCaptureOperation, client_operation_id=operation_id) == 1
    assert count(Evidence, id=evidence_id) == 1

    retry = sync(str(officer.id), operation_id, data=payload, **fields)
    assert retry.status_code == 200
    assert retry.json()["evidence_id"] == evidence_id


def test_a_database_failure_while_finalizing_answers_temporarily_unavailable(
        harness, monkeypatch):
    """F-SE-06 (Stage E): a lost database mid-finalization is 503, never a 500.

    The audit write flushes the pending ACCEPTED update, so it is the first
    place the dependency can fail after the reused pipeline has committed its
    own row. Design 6 promises ``temporarily_unavailable`` for that and design
    12 forbids a 500, while R1 requires the identity to stay *undecided* so a
    retry can still settle it.
    """
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "finalize-fault")
    started = datetime.now(timezone.utc)
    operation_id = op_id()
    fields = dict(session_id=session["id"], captured_at=now_iso(-60),
                  latitude="53.3498", longitude="-6.2603", location_source="DEVICE_GPS")

    def refused_audit(*args, **kwargs):
        raise OperationalError("INSERT INTO audit_ledger_events", {},
                               Exception("database connection lost"))

    monkeypatch.setattr(field_service, "_audit", refused_audit)

    response = sync(str(officer.id), operation_id, **fields)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["sync_status"] == "temporarily_unavailable"

    stored = rows(FieldCaptureOperation, client_operation_id=operation_id)
    assert len(stored) == 1
    assert stored[0].status == "PENDING"
    assert stored[0].evidence_id is None
    assert events("FIELD_SYNC_ACCEPTED", resource_id=str(stored[0].id)) == []

    # ``ingest_evidence`` commits in its own transaction (design 5), so the
    # refused finalization leaves exactly one real, unlinked quarantine row.
    stranded = [row for row in rows(Evidence, project_id=None)
                if row.created_at >= started]
    for row in stranded:
        harness.track_evidence(str(row.id))
    assert len(stranded) == 1

    monkeypatch.undo()
    in_flight = sync(str(officer.id), operation_id, **fields)
    assert in_flight.status_code == 503, in_flight.text
    assert in_flight.json()["detail"]["sync_status"] == "temporarily_unavailable"
    assert count(FieldCaptureOperation, client_operation_id=operation_id) == 1


def test_unsupported_sync_fields_are_refused_not_ignored(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "fields")
    smuggled = sync(str(officer.id), op_id(),
                    extra_fields={"project_id": project["id"], "role": "ADMINISTRATOR"},
                    session_id=session["id"])
    assert smuggled.status_code == 422
    detail = smuggled.json()["detail"]
    assert detail["sync_status"] == "validation_failed"
    assert "UNEXPECTED_FIELD_PROJECT_ID" in detail["validation_errors"]
    assert "UNEXPECTED_FIELD_ROLE" in detail["validation_errors"]
    assert count(FieldCaptureOperation, user_id=str(officer.id)) == 0

    short = sync(str(officer.id), "abc123", session_id=session["id"])
    assert short.status_code == 422
    assert short.json()["detail"]["validation_errors"] == ["CLIENT_OPERATION_ID_TOO_SHORT"]


# ---------------------------------------------------------------------------
# evidence pipeline reuse and metadata semantics
# ---------------------------------------------------------------------------

def test_existing_ingestion_validator_decides_rejections(harness, monkeypatch):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "validate")

    mismatched = sync(str(officer.id), op_id(), data=png_bytes(),
                      content_type="image/jpeg", session_id=session["id"])
    assert mismatched.status_code == 415  # the existing validator's contract

    monkeypatch.setattr(settings, "max_upload_size", 32)
    oversized_op = op_id()
    oversized = sync(str(officer.id), oversized_op, data=jpeg_bytes() * 8,
                     session_id=session["id"])
    assert oversized.status_code == 413

    assert count(Evidence, project_id=project["id"]) == 0
    # A structural rejection is not a durable decision: the reused validator
    # raises before it stores anything, so the reservation is dropped and the
    # operation identity stays retryable (design §6 table, "none (rollback)").
    assert count(FieldCaptureOperation, user_id=str(officer.id)) == 0

    replay = sync(str(officer.id), oversized_op, data=jpeg_bytes() * 8,
                  session_id=session["id"])
    assert replay.status_code == 413
    assert count(FieldCaptureOperation, client_operation_id=oversized_op) == 0

    # The same identity can still land once the file is fixable.
    monkeypatch.undo()  # back to the real upload limit
    recovered = sync(str(officer.id), oversized_op, data=jpeg_bytes(),
                     session_id=session["id"])
    assert recovered.status_code == 201, recovered.text
    harness.track_evidence(recovered.json()["evidence_id"])
    assert count(FieldCaptureOperation, client_operation_id=oversized_op) == 1


def test_operation_digest_equals_the_fingerprint_the_analysis_job_computes(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "digest")
    payload = jpeg_bytes()
    accepted = sync(str(officer.id), op_id(), data=payload, session_id=session["id"])
    evidence_id = harness.track_evidence(accepted.json()["evidence_id"])
    operation = rows(FieldCaptureOperation, id=accepted.json()["operation_id"])[0]

    db = get_session()
    try:
        result = process_evidence(evidence_id, db)
        evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one()
        # The reused analysis pipeline re-downloads the stored bytes and hashes
        # them; BE-026 adds no second SHA-256 implementation, so the two agree.
        assert evidence.sha256 == result.sha256
        assert evidence.sha256 == operation.payload_sha256
    finally:
        db.close()


def test_retention_purge_of_a_field_capture_leaves_the_operation_readable(harness):
    """DEF-C-03 regression: purging a field-synced capture must not be blocked.

    ``retention.py:1175-1176`` deletes the metadata rows and then the Evidence
    row, relying on this table's ``ON DELETE SET NULL``. While an
    ``ACCEPTED implies evidence_id IS NOT NULL`` CHECK existed, Postgres
    rejected that nulling and aborted the purge -- and every later UPDATE of
    the operation row with it. The invariant belongs to the service (an
    accepted row is written with its evidence id in the same statement), so
    the reference has to be allowed to clear while the record survives.
    """
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "purge")
    operation_id = op_id()
    accepted = sync(str(officer.id), operation_id, data=jpeg_bytes(),
                    session_id=session["id"])
    assert accepted.status_code == 201, accepted.text
    evidence_id = harness.track_evidence(accepted.json()["evidence_id"])
    row_id = accepted.json()["operation_id"]

    db = get_session()
    try:
        db.query(EvidenceMetadata).filter(
            EvidenceMetadata.evidence_id == evidence_id).delete(synchronize_session=False)
        db.query(Evidence).filter(
            Evidence.id == evidence_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    surviving = rows(FieldCaptureOperation, id=row_id)[0]
    assert surviving.status == "ACCEPTED"
    assert surviving.evidence_id is None
    assert surviving.client_operation_id == operation_id
    assert count(FieldCaptureOperation, client_operation_id=operation_id) == 1

    # A later replay must still be able to write the row.
    db = get_session()
    try:
        live = db.query(FieldCaptureOperation).filter_by(id=row_id).one()
        live.sync_count = 2
        db.commit()
    finally:
        db.close()
    assert rows(FieldCaptureOperation, id=row_id)[0].sync_count == 2


def test_missing_gps_is_captured_as_unlocated_not_as_zero_island(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "nogps")
    accepted = sync(str(officer.id), op_id(), session_id=session["id"],
                    captured_at=now_iso(-90), queued_at=now_iso(-88))
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()
    assert body["location"]["reported"] is False
    assert body["location"]["latitude"] is None
    assert body["location"]["location_source"] is None
    harness.track_evidence(body["evidence_id"])

    db = get_session()
    try:
        location = db.execute(
            text("SELECT location FROM evidence WHERE id=:i"),
            {"i": body["evidence_id"]},
        ).scalar()
    finally:
        db.close()
    assert location is None


def test_unusable_metadata_is_refused_durably_and_replayed_exactly(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "meta")
    operation_id = op_id()
    naive = sync(str(officer.id), operation_id, session_id=session["id"],
                 captured_at="2026-10-01T12:00:00")
    assert naive.status_code == 422
    assert naive.json()["sync_status"] == "validation_failed"
    assert "CAPTURED_AT_NAIVE_TIMESTAMP" in naive.json()["validation_errors"]
    assert count(Evidence, project_id=project["id"]) == 0

    replay = sync(str(officer.id), operation_id, session_id=session["id"],
                  captured_at="2026-10-01T12:00:00")
    assert replay.status_code == 422
    assert replay.json()["sync_status"] == "validation_failed"
    assert count(FieldCaptureOperation, client_operation_id=operation_id) == 1

    half_fix = op_id()
    partial = sync(str(officer.id), half_fix, session_id=session["id"],
                   latitude="53.3498", location_source="DEVICE_GPS")
    assert partial.status_code == 422
    assert "GPS_PARTIAL_FIX" in partial.json()["validation_errors"]
    stored = rows(FieldCaptureOperation, client_operation_id=half_fix)[0]
    assert stored.latitude is None and stored.longitude is None

    zero_island = sync(str(officer.id), op_id(), session_id=session["id"],
                       latitude="0", longitude="0", location_source="DEVICE_MANUAL")
    assert zero_island.status_code == 422
    assert "ZERO_ISLAND_UNCONFIRMED" in zero_island.json()["validation_errors"]


def test_confirmed_zero_island_and_anomalous_ordering_are_stored_not_rewritten(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "flags")
    captured, queued, uploaded = now_iso(120), now_iso(-300), now_iso(-200)
    response = sync(str(officer.id), op_id(), session_id=session["id"],
                    latitude="0", longitude="0", zero_island_confirmed="true",
                    location_source="DEVICE_MANUAL",
                    captured_at=captured, queued_at=queued, uploaded_at=uploaded)
    assert response.status_code == 201, response.text
    body = response.json()
    harness.track_evidence(body["evidence_id"])
    assert body["location"]["reported"] is True
    assert body["location"]["zero_island_confirmed"] is True
    assert "FUTURE_CAPTURE" in body["timestamp_flags"]
    assert "QUEUE_BEFORE_CAPTURE" in body["timestamp_flags"]
    # The values are stored exactly as asserted, anomaly labels aside.
    assert body["captured_at"].startswith(captured[:16])
    assert body["queued_at"].startswith(queued[:16])
    assert body["uploaded_at"].startswith(uploaded[:16])


# ---------------------------------------------------------------------------
# conflict taxonomy
# ---------------------------------------------------------------------------

def test_assignment_revoked_while_offline_conflicts_explicitly(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "revoke")
    revoke = client.patch(
        f"/api/v1/field/assignments/{assignment['id']}/status",
        json={"status": "REVOKED", "reason": "safety stand-down"},
        headers=headers_for(str(admin.id)),
    )
    assert revoke.status_code == 200

    queued = sync(str(officer.id), op_id(), session_id=session["id"],
                  captured_at=now_iso(-60))
    assert queued.status_code == 409
    body = queued.json()
    assert body["sync_status"] == "conflict"
    assert body["conflict_reason"] == "ASSIGNMENT_REVOKED"
    assert body["status"] == "CONFLICT"
    assert body["evidence_id"] is None
    assert count(Evidence, project_id=project["id"]) == 0

    conflict = events("FIELD_SYNC_CONFLICT", resource_id=body["operation_id"])[-1]
    assert conflict["payload"]["conflict_reason"] == "ASSIGNMENT_REVOKED"
    assert conflict["payload"]["affected_resource"] == assignment["id"]
    assert conflict["payload"]["server_state"]["assignment_status"] == "REVOKED"
    assert conflict["payload"]["resolution_status"] == "UNRESOLVED"


def test_expired_assignment_conflicts_after_the_device_queued(harness):
    admin, org, project, officer = officer_world(harness, "expired")
    assignment = new_assignment(user_id=str(officer.id), project_id=project["id"],
                                expires_at=now_iso(30))
    session = open_session(str(officer.id), assignment["id"]).json()

    # The deadline passes while the device is out of coverage.
    db = get_session()
    try:
        db.execute(
            text("UPDATE field_assignments SET expires_at = :past WHERE id = :id"),
            {"past": datetime.now(timezone.utc) - timedelta(minutes=1),
             "id": assignment["id"]},
        )
        db.commit()
    finally:
        db.close()

    queued = sync(str(officer.id), op_id(), session_id=session["id"])
    assert queued.status_code == 409
    assert queued.json()["conflict_reason"] == "ASSIGNMENT_EXPIRED"
    assert rows(FieldAssignment, id=assignment["id"])[0].status == "EXPIRED"
    assert events("FIELD_ASSIGNMENT_EXPIRED", resource_id=assignment["id"])


def test_closed_session_conflicts_for_captures_queued_before_closure(harness):
    admin, org, project, officer = officer_world(harness, "sess-close")
    assignment = new_assignment(user_id=str(officer.id), project_id=project["id"])
    session = open_session(str(officer.id), assignment["id"]).json()
    client.post(f"/api/v1/field/sessions/{session['id']}/close",
                json={"reason": "shift end"}, headers=headers_for(str(officer.id)))

    queued = sync(str(officer.id), op_id(), session_id=session["id"])
    assert queued.status_code == 409
    assert queued.json()["conflict_reason"] == "SESSION_CLOSED"
    assert count(Evidence, project_id=project["id"]) == 0


def test_operation_identity_bound_to_another_session_conflicts(harness):
    admin, org, project, officer = officer_world(harness, "bind")
    first_assignment = new_assignment(user_id=str(officer.id), project_id=project["id"],
                                      claim_id=None)
    first_session = open_session(str(officer.id), first_assignment["id"],
                                 client_device_id="device-a").json()

    # A second ACTIVE assignment is needed to open a second session.
    claim_id = harness.claim(project["id"], str(officer.id))
    second_assignment = new_assignment(user_id=str(officer.id), project_id=project["id"],
                                       claim_id=claim_id)
    second_session = open_session(str(officer.id), second_assignment["id"],
                                  client_device_id="device-b").json()

    operation_id = op_id()
    accepted = sync(str(officer.id), operation_id, session_id=first_session["id"],
                    latitude="53.3498", longitude="-6.2603", location_source="DEVICE_GPS")
    assert accepted.status_code == 201, accepted.text
    evidence_id = harness.track_evidence(accepted.json()["evidence_id"])

    moved = sync(str(officer.id), operation_id, session_id=second_session["id"],
                 latitude="53.3498", longitude="-6.2603", location_source="DEVICE_GPS")
    assert moved.status_code == 409
    assert moved.json()["sync_status"] == "conflict"
    assert count(Evidence, id=evidence_id) == 1
    stored = rows(FieldCaptureOperation, id=accepted.json()["operation_id"])[0]
    assert stored.session_id == first_session["id"]
    assert stored.status == "ACCEPTED"


def test_sync_against_a_mismatched_session_is_denied_not_crashed(harness):
    """DEF-C-01 runtime proof for the defensive FOREIGN_ASSIGNMENT denial.

    The service only mints a session from the caller's own assignment, so a
    session owned by the officer but bound to someone else's assignment cannot
    be created through the API. It is inserted directly here to exercise the
    branch that used to call ``_deny`` with a keyword it does not accept --
    which would have answered 500 instead of 404.
    """
    admin, org, project, officer = officer_world(harness, "mismatched")
    colleague = harness.user("mismatched-colleague")
    grant(str(colleague.id), "FIELD_OFFICER", "ORGANIZATION", str(org.id))
    theirs = new_assignment(user_id=str(colleague.id), project_id=project["id"])

    forged = str(uuid4())
    db = get_session()
    try:
        db.execute(
            text("INSERT INTO field_sessions (id, assignment_id, user_id, project_id, status)"
                 " VALUES (:id, :assignment, :user, :project, 'ACTIVE')"),
            {"id": forged, "assignment": theirs["id"], "user": str(officer.id),
             "project": project["id"]},
        )
        db.commit()
    finally:
        db.close()

    denied = sync(str(officer.id), op_id(), session_id=forged)
    assert denied.status_code == 404, denied.text
    assert denied.json()["detail"]["sync_status"] == "authorization_denied"
    assert denied.json()["detail"]["message"] == "Not found"

    # R2: a denial never mutates domain state.
    assert count(FieldCaptureOperation, user_id=str(officer.id)) == 0
    assert count(Evidence, project_id=project["id"]) == 0

    rejected = events("FIELD_SYNC_REJECTED")[-1]
    assert rejected["payload"]["failure"] == "FOREIGN_ASSIGNMENT"
    assert rejected["payload"]["session_id"] == forged
    assert rejected["payload"]["assignment_id"] == theirs["id"]
    assert rejected["actor_id"] == str(officer.id)
    security = events("FIELD_ASSIGNMENT_SECURITY_FAILURE")[-1]
    assert security["payload"]["failure"] == "FOREIGN_ASSIGNMENT"
    assert security["resource_id"] == theirs["id"]


def test_superseded_assignment_conflicts(harness):
    admin, org, project, officer = officer_world(harness, "supersede")
    claim_id = harness.claim(project["id"], str(officer.id))
    old_assignment = new_assignment(user_id=str(officer.id), project_id=project["id"],
                                    claim_id=claim_id)
    old_session = open_session(str(officer.id), old_assignment["id"],
                               client_device_id="device-a").json()

    # Same claim, so the claim-scoped partial index allows exactly one ACTIVE
    # row: release the old one first, then issue the replacement.
    client.patch(f"/api/v1/field/assignments/{old_assignment['id']}/status",
                 json={"status": "REVOKED", "reason": "replaced"},
                 headers=headers_for(str(admin.id)))
    new_assignment(user_id=str(officer.id), project_id=project["id"], claim_id=claim_id)

    queued = sync(str(officer.id), op_id(), session_id=old_session["id"])
    assert queued.status_code == 409
    assert queued.json()["conflict_reason"] in {"ASSIGNMENT_REVOKED",
                                                 "ASSIGNMENT_SUPERSEDED"}


def test_missing_context_resource_is_explicit_never_silent(harness, monkeypatch):
    """CONTEXT_RESOURCE_MISSING is defensive: nothing in the API deletes a claim.

    The guard is exercised by forcing the context lookup to report the claim as
    gone, which is exactly the state a partially-failed import would leave.
    """
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "missing")
    monkeypatch.setattr(field_service.field_repo, "claims_by_ids",
                        lambda db, ids: {})

    response = sync(str(officer.id), op_id(), session_id=session["id"],
                    captured_at=now_iso(-30))
    assert response.status_code == 409
    body = response.json()
    assert body["conflict_reason"] == "CONTEXT_RESOURCE_MISSING"
    operation = rows(FieldCaptureOperation, id=body["operation_id"])[0]
    assert operation.claim_id == claim_id
    conflict = events("FIELD_SYNC_CONFLICT", resource_id=body["operation_id"])[-1]
    assert conflict["payload"]["server_state"]["missing_claim_id"] == claim_id


def test_ambiguous_active_assignments_require_a_session_and_leave_no_row(harness):
    admin, org, project, officer = officer_world(harness, "ambiguous")
    first_claim = harness.claim(project["id"], str(officer.id))
    second_claim = harness.claim(project["id"], str(officer.id))
    new_assignment(user_id=str(officer.id), project_id=project["id"],
                   claim_id=first_claim)
    new_assignment(user_id=str(officer.id), project_id=project["id"],
                   claim_id=second_claim)

    response = sync(str(officer.id), op_id(), captured_at=now_iso(-30))
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["sync_status"] == "validation_failed"
    assert "AMBIGUOUS_ACTIVE_ASSIGNMENT" in detail["validation_errors"]
    # Correctable, so the identity stays free: no durable row.
    assert count(FieldCaptureOperation, user_id=str(officer.id)) == 0

    session = open_session(str(officer.id), client.get(
        "/api/v1/field/work", headers=headers_for(str(officer.id))
    ).json()["items"][0]["assignment_id"], client_device_id="device-a").json()
    accepted = sync(str(officer.id), op_id(), session_id=session["id"],
                    captured_at=now_iso(-30))
    assert accepted.status_code == 201, accepted.text
    harness.track_evidence(accepted.json()["evidence_id"])


# ---------------------------------------------------------------------------
# conflict resolution (manager-only)
# ---------------------------------------------------------------------------

def resolved_conflict(harness, label: str):
    admin, org, project, officer, assignment, session, claim_id = prepared(harness, label)
    client.patch(f"/api/v1/field/assignments/{assignment['id']}/status",
                 json={"status": "REVOKED", "reason": "stand down"},
                 headers=headers_for(str(admin.id)))
    conflict = sync(str(officer.id), op_id(), session_id=session["id"]).json()
    return admin, officer, conflict


def test_conflict_resolution_is_administrative_and_non_mutating(harness):
    admin, officer, conflict = resolved_conflict(harness, "resolve")
    operation_id = conflict["operation_id"]
    evidence_count_before = count(Evidence)

    denied = client.post(f"/api/v1/field/operations/{operation_id}/resolve",
                         json={"outcome": "DISMISSED", "note": "mine"},
                         headers=headers_for(str(officer.id)))
    assert denied.status_code == 403

    resolved = client.post(f"/api/v1/field/operations/{operation_id}/resolve",
                           json={"outcome": "RESUBMISSION_REQUIRED",
                                 "note": "queued against a stood-down assignment"},
                           headers=headers_for(str(admin.id)))
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["resolution_status"] == "RESOLVED"
    assert body["resolution_outcome"] == "RESUBMISSION_REQUIRED"
    # The conflict fields survive as the historical record.
    assert body["conflict_reason"] == "ASSIGNMENT_REVOKED"
    assert body["status"] == "CONFLICT"
    assert body["resolved_by"] == str(admin.id)
    assert count(Evidence) == evidence_count_before

    again = client.post(f"/api/v1/field/operations/{operation_id}/resolve",
                        json={"outcome": "DISMISSED", "note": "twice"},
                        headers=headers_for(str(admin.id)))
    assert again.status_code == 409

    audit = events("FIELD_SYNC_CONFLICT_RESOLVED", resource_id=operation_id)[-1]
    assert audit["actor_id"] == str(admin.id)
    assert audit["payload"]["resolution_outcome"] == "RESUBMISSION_REQUIRED"

    bad = client.post(f"/api/v1/field/operations/{operation_id}/resolve",
                      json={"outcome": "INGEST_ANYWAY", "note": "no"},
                      headers=headers_for(str(admin.id)))
    assert bad.status_code == 422


def test_manager_operation_listing_sees_conflicts_and_filters(harness):
    admin, officer, conflict = resolved_conflict(harness, "list")
    listed = client.get("/api/v1/field/operations",
                        params={"status": "CONFLICT"},
                        headers=headers_for(str(admin.id)))
    assert listed.status_code == 200
    body = listed.json()
    assert conflict["operation_id"] in [item["id"] for item in body["items"]]
    assert body["total"] >= 1

    unresolved = client.get("/api/v1/field/operations",
                            params={"resolution_status": "UNRESOLVED",
                                    "status": "CONFLICT"},
                            headers=headers_for(str(admin.id))).json()
    assert conflict["operation_id"] in [item["id"] for item in unresolved["items"]]

    by_user = client.get("/api/v1/field/operations",
                         params={"user_id": str(officer.id)},
                         headers=headers_for(str(admin.id))).json()
    assert by_user["total"] >= 1

    assert client.get("/api/v1/field/operations",
                      params={"user_id": "not-a-uuid"},
                      headers=headers_for(str(admin.id))).status_code == 422


# ---------------------------------------------------------------------------
# authorization matrix, enforce mode
# ---------------------------------------------------------------------------

def test_role_matrix_in_enforcing_mode(harness):
    admin, org, project, officer = officer_world(harness, "matrix")
    assignment = new_assignment(user_id=str(officer.id), project_id=project["id"])
    session_id = open_session(str(officer.id), assignment["id"]).json()["id"]

    with enforcing():
        # FIELD_OFFICER with a covering grant: permitted.
        allowed = sync(str(officer.id), op_id(), session_id=session_id)
        assert allowed.status_code == 201, allowed.text
        harness.track_evidence(allowed.json()["evidence_id"])

        for role in ("REVIEWER", "SUPERVISOR", "CITIZEN"):
            user = harness.user(f"matrix-{role}")
            grant(str(user.id), role, "ORGANIZATION", str(org.id))
            denied = sync(str(user.id), op_id(), session_id=None)
            assert denied.status_code == 403, (role, denied.text)
            # A denial never creates a row, for any role.
            assert count(FieldCaptureOperation, user_id=str(user.id)) == 0

        # ADMINISTRATOR has the management permission but not field.sync.
        assert sync(str(admin.id), op_id()).status_code == 403
        assert client.get("/api/v1/field/operations",
                          headers=headers_for(str(admin.id))).status_code == 200
        # ...and SUPERVISOR gets neither in BE-026 (existing semantics unchanged).
        supervisor = harness.user("matrix-super")
        grant(str(supervisor.id), "SUPERVISOR", "GLOBAL")
        assert client.get("/api/v1/field/assignments",
                          headers=headers_for(str(supervisor.id))).status_code == 403

        # Unauthenticated is 401, never anonymous access.
        assert client.post("/api/v1/field/sync",
                           files={"file": ("c.jpg", jpeg_bytes(), "image/jpeg")},
                           data={"client_operation_id": op_id()}).status_code == 401
        assert client.get("/api/v1/field/work").status_code == 401


def test_api_client_requires_explicit_scopes_and_still_needs_an_assignment(harness):
    admin, org, project, officer = officer_world(harness, "apiclient")
    with enforcing():
        scoped = client.post("/api/v1/auth/clients",
                             json={"name": f"be026-scoped-{uuid4().hex[:8]}",
                                   "scopes": ["field.sync", "evidence.create"]},
                             headers=headers_for(str(admin.id)))
        assert scoped.status_code == 201
        scoped_id = harness.track_client(scoped.json()["id"])

        # The scope grants the permission, but assignments bind to principals:
        # a client with no assignment of its own is refused, not trusted.
        refused = client.post(
            "/api/v1/field/sync",
            headers=client_headers(scoped_id),
            files={"file": ("c.jpg", jpeg_bytes(), "image/jpeg")},
            data={"client_operation_id": op_id()},
        )
        assert refused.status_code == 403
        assert refused.json()["detail"]["sync_status"] == "authorization_denied"
        assert count(FieldCaptureOperation, user_id=scoped_id) == 0

        narrow = client.post("/api/v1/auth/clients",
                             json={"name": f"be026-narrow-{uuid4().hex[:8]}",
                                   "scopes": ["evidence.read"]},
                             headers=headers_for(str(admin.id)))
        narrow_id = harness.track_client(narrow.json()["id"])
        assert client.get("/api/v1/field/work",
                          headers=client_headers(narrow_id)).status_code == 403


def test_assignment_is_not_authority_in_two_directions(harness):
    admin, org, project, officer = officer_world(harness, "authority")
    other_org = harness.org("authority-other")
    other_project = harness.project(str(admin.id), "authority-other-proj",
                                    org_id=str(other_org.id))

    with enforcing():
        # (a) ACTIVE assignment + permission, but the role grant does not cover
        # the assignment's project: denied at the scope gate, and no row.
        outside = harness.user("authority-outside")
        grant(str(outside.id), "FIELD_OFFICER", "PROJECT", project["id"])
        stray = new_assignment(user_id=str(outside.id), project_id=other_project["id"],
                               actor_id=str(admin.id))
        stray_session = open_session(str(outside.id), stray["id"])
        assert stray_session.status_code == 404
        assert stray_session.json()["detail"]["sync_status"] == "authorization_denied"
        assert count(FieldSession, assignment_id=stray["id"]) == 0

        stray_sync = sync(str(outside.id), op_id(), captured_at=now_iso(-10))
        assert stray_sync.status_code == 404
        assert count(FieldCaptureOperation, user_id=str(outside.id)) == 0

        # (b) role grant + no assignment: the feed is empty and syncing is 403.
        unassigned = harness.user("authority-unassigned")
        grant(str(unassigned.id), "FIELD_OFFICER", "ORGANIZATION", str(org.id))
        assert client.get("/api/v1/field/work",
                          headers=headers_for(str(unassigned.id))).json()["total"] == 0
        denied = sync(str(unassigned.id), op_id())
        assert denied.status_code == 403
        assert denied.json()["detail"]["sync_status"] == "authorization_denied"
        assert count(FieldCaptureOperation, user_id=str(unassigned.id)) == 0


def test_owner_surfaces_refuse_the_development_bypass(harness):
    # Owner-scoped routes bind rows to an identified officer, so the anonymous
    # development bypass must not obtain a work feed or a capture.
    assert client.get("/api/v1/field/work").status_code == 401
    assert client.post("/api/v1/field/sync",
                       files={"file": ("c.jpg", jpeg_bytes(), "image/jpeg")},
                       data={"client_operation_id": op_id()}).status_code == 401
    assert client.get(f"/api/v1/field/captures/{op_id()}").status_code == 401


def test_suspended_officer_cannot_sync(harness):
    admin, org, project, officer = officer_world(harness, "suspend")
    assignment = new_assignment(user_id=str(officer.id), project_id=project["id"])
    session_id = open_session(str(officer.id), assignment["id"]).json()["id"]
    db = get_session()
    try:
        db.query(User).filter(User.id == str(officer.id)).update({"status": "SUSPENDED"})
        db.commit()
    finally:
        db.close()

    with enforcing():
        assert sync(str(officer.id), op_id(), session_id=session_id).status_code == 401


# ---------------------------------------------------------------------------
# audit obligations
# ---------------------------------------------------------------------------

def test_field_audit_trail_is_complete_chained_and_secret_free(harness):
    admin, org, project, officer = officer_world(harness, "audit")
    claim_id = harness.claim(project["id"], str(officer.id))
    payload = jpeg_bytes()

    assignment = new_assignment(user_id=str(officer.id), project_id=project["id"],
                                claim_id=claim_id)
    session_id = open_session(str(officer.id), assignment["id"],
                              client_device_id="pixel-7").json()["id"]
    operation_id = op_id()
    accepted = sync(str(officer.id), operation_id, data=payload,
                    session_id=session_id, latitude="53.3498", longitude="-6.2603",
                    location_source="DEVICE_GPS")
    assert accepted.status_code == 201
    evidence_id = harness.track_evidence(accepted.json()["evidence_id"])
    sync(str(officer.id), operation_id, data=payload, session_id=session_id,
         latitude="53.3498", longitude="-6.2603", location_source="DEVICE_GPS")
    client.post(f"/api/v1/field/sessions/{session_id}/close",
                json={"reason": "end of shift"}, headers=headers_for(str(officer.id)))
    client.get("/api/v1/field/assignments", headers=headers_for(str(admin.id)))
    client.patch(f"/api/v1/field/assignments/{assignment['id']}/status",
                 json={"status": "REVOKED", "reason": "post-audit stand-down"},
                 headers=headers_for(str(admin.id)))

    created = events("FIELD_ASSIGNMENT_CREATED", resource_id=assignment["id"])[-1]
    assert created["project_id"] == project["id"]
    assert created["resource_type"] == "field_assignment"
    assert events("FIELD_SESSION_OPENED", resource_id=session_id)
    assert events("FIELD_SESSION_CLOSED", resource_id=session_id)
    assert events("FIELD_SYNC_DUPLICATE")
    assert events("FIELD_ASSIGNMENT_ACCESSED")
    assert events("FIELD_ASSIGNMENT_STATUS_CHANGED", resource_id=assignment["id"])

    # No bytes, tokens, credentials or URLs in any field payload.
    field_events = []
    db = get_session()
    try:
        field_events = (
            db.query(AuditLedgerEvent)
            .filter(AuditLedgerEvent.event_type.in_(FIELD_EVENT_TYPES))
            .all()
        )
        serialized = " ".join(
            json.dumps(row.payload, default=str) for row in field_events
        )
    finally:
        db.close()
    for forbidden in (b"JFIF".decode(), "data:image", "Bearer", "dev-user-",
                      "dev-client-", "presigned", "password", "secret"):
        assert forbidden not in serialized, forbidden
    assert "storage_key" not in serialized

    db = get_session()
    try:
        chain = audit_service.verify_chain(db)
    finally:
        db.close()
    assert chain["valid"] is True, chain


def test_audit_ledger_records_denied_synchronizations_without_a_row(harness):
    admin, org, project, officer = officer_world(harness, "denied-audit")
    stranger = harness.user("denied-audit-stranger")
    grant(str(stranger.id), "FIELD_OFFICER", "GLOBAL")

    with enforcing():
        denied = sync(str(stranger.id), op_id())
        assert denied.status_code == 403

    assert count(FieldCaptureOperation, user_id=str(stranger.id)) == 0
    rejected = events("FIELD_SYNC_REJECTED")[-1]
    assert rejected["actor_id"] == str(stranger.id)
    assert rejected["payload"]["failure"] == "NO_ACTIVE_ASSIGNMENT"
    assert rejected["payload"]["status"] == "authorization_denied"
    security = events("FIELD_ASSIGNMENT_SECURITY_FAILURE")[-1]
    assert security["payload"]["failure"] == "NO_ACTIVE_ASSIGNMENT"


# ---------------------------------------------------------------------------
# schema-level guarantees (the constraint the service relies on)
# ---------------------------------------------------------------------------

def test_operation_identity_unique_constraint_is_enforced_by_the_database(harness):
    admin, org, project, officer, assignment, session, claim_id = prepared(
        harness, "constraint")
    operation_id = op_id()
    accepted = sync(str(officer.id), operation_id, session_id=session["id"])
    harness.track_evidence(accepted.json()["evidence_id"])

    db = get_session()
    try:
        with pytest.raises(Exception):
            db.execute(
                text("INSERT INTO field_capture_operations ("
                     " id, user_id, client_operation_id, request_hash,"
                     " payload_sha256, file_size, status, received_at)"
                     " VALUES (:id, :user_id, :op, :hash, :digest, 1,"
                     " 'ACCEPTED', now())"),
                {"id": str(uuid4()), "user_id": str(officer.id), "op": operation_id,
                 "hash": "0" * 64, "digest": "0" * 64},
            )
        db.rollback()
    finally:
        db.close()

    # A different officer may reuse the same client label: the identity is
    # (officer, client_operation_id), not the label alone.
    other = harness.user("constraint-other")
    grant(str(other.id), "FIELD_OFFICER", "ORGANIZATION", str(org.id))
    other_assignment = new_assignment(user_id=str(other.id), project_id=project["id"])
    other_session = open_session(str(other.id), other_assignment["id"]).json()
    response = sync(str(other.id), operation_id, session_id=other_session["id"])
    assert response.status_code == 201
    harness.track_evidence(response.json()["evidence_id"])
    assert count(FieldCaptureOperation, client_operation_id=operation_id) == 2
