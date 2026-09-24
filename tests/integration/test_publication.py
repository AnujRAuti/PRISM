"""BE-022 integration tests against real PostgreSQL infrastructure.

Exercises the publication governance surface end to end (§39): policy
creation, request lifecycle, releasability evaluation, approval separation,
publishing, public retrieval and listing, pagination, identifier stability,
version immutability, unpublication, cross-project isolation, privacy
protection (storage keys / EXIF / GPS), dispute and correction interaction,
retention interaction, audit event creation, and authorization enforcement.

The unauthenticated TestClient runs in development-bypass mode, so actor
identities are supplied explicitly. Authenticated tests use
``Bearer dev-user-{id}`` headers with real role assignments.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.db.models import (
    Activity,
    AuditLedgerEvent,
    Claim,
    CorrectionRequest,
    Dispute,
    Evidence,
    EvidenceMetadata,
    Project,
    Publication,
    PublicationEvent,
    PublicationPolicy,
    PublicationPolicyVersion,
    PublicationVersion,
    PublicIdentifier,
    RetentionHold,
    User,
)
from backend.db.session import get_session
from backend.services import authorization as auth_service


client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def setup_user() -> User:
    session = get_session()
    user = User(username=f"be022-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def headers_for(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def assign(user_id: str, role: str, scope: str = "GLOBAL", scope_id: str | None = None):
    session = get_session()
    try:
        kwargs: dict = {}
        if scope == "PROJECT":
            kwargs["project_id"] = scope_id
        row, _ = auth_service.assign_role(
            session, user_id=user_id, role_name=role, scope_type=scope, **kwargs
        )
        session.commit()
        return row
    finally:
        session.close()


def api_create_project(user_id: str, name: str = "BE-022 project") -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": user_id})
    assert response.status_code == 201, response.text
    return response.json()


def create_policy(target_types=("PROJECT", "EVIDENCE"), **overrides) -> dict:
    body = {
        "name": f"be022-policy-{uuid4()}",
        "description": "BE-022 test policy",
        "version": "1.0",
        "allowed_target_types": list(target_types),
        "public_fields": ["public_id", "name", "title"],
        "prohibited_fields": ["storage_key", "exif"],
        "allow_media_exposure": False,
        "allow_derived_intelligence": False,
        "allow_review_outcomes": False,
        "min_authorization_level": "REVIEWER",
        "required_approvals": 1,
        "require_separation_of_duties": True,
        "location_precision": "HIDDEN",
        "redaction_level": "STANDARD",
    }
    body.update(overrides)
    response = client.post("/api/v1/publications/policies", json=body)
    assert response.status_code in (200, 201), response.text
    return response.json()


def run_to_published(policy: dict, target_type: str, target_id: str, requester, approver) -> dict:
    """Drive a publication request through review -> approve -> publish."""
    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": target_type,
            "target_id": target_id,
            "policy_id": policy["id"],
            "reason": "BE-022 integration test",
        },
        headers=headers_for(str(requester.id)),
    )
    assert response.status_code in (200, 201), response.text
    publication = response.json()

    response = client.post(
        f"/api/v1/publications/{publication['id']}/submit-review",
        headers=headers_for(str(requester.id)),
    )
    assert response.status_code == 200, response.text

    response = client.post(
        f"/api/v1/publications/{publication['id']}/approve",
        headers=headers_for(str(approver.id)),
    )
    assert response.status_code == 200, response.text

    response = client.post(
        f"/api/v1/publications/{publication['id']}/publish",
        headers=headers_for(str(approver.id)),
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Policy (§9)
# ---------------------------------------------------------------------------


def test_create_publication_policy():
    user = setup_user()
    assign(str(user.id), "ADMINISTRATOR")
    policy = create_policy()
    assert policy["name"].startswith("be022-policy-")
    assert policy["status"] == "ACTIVE"
    assert policy["version"] == "1.0"


def test_policy_name_is_idempotent():
    user = setup_user()
    assign(str(user.id), "ADMINISTRATOR")
    name = f"be022-idem-{uuid4()}"
    first = client.post(
        "/api/v1/publications/policies",
        json={"name": name, "version": "1.0", "allowed_target_types": ["PROJECT"]},
    )
    assert first.status_code in (200, 201), first.text
    second = client.post(
        "/api/v1/publications/policies",
        json={"name": name, "version": "1.0", "allowed_target_types": ["PROJECT"]},
    )
    assert second.status_code in (200, 201), second.text
    assert second.json()["id"] == first.json()["id"]


def test_policy_rejects_unknown_target_type():
    user = setup_user()
    assign(str(user.id), "ADMINISTRATOR")
    response = client.post(
        "/api/v1/publications/policies",
        json={"name": f"bad-{uuid4()}", "version": "1.0", "allowed_target_types": ["NOT_A_TYPE"]},
    )
    assert response.status_code == 422, response.text


def test_policy_manage_requires_permission():
    plain = setup_user()  # no roles
    response = client.post(
        "/api/v1/publications/policies",
        json={"name": f"denied-{uuid4()}", "version": "1.0", "allowed_target_types": ["PROJECT"]},
        headers=headers_for(str(plain.id)),
    )
    assert response.status_code in (401, 403), response.text


# ---------------------------------------------------------------------------
# Lifecycle (§6, §7)
# ---------------------------------------------------------------------------


def test_publication_lifecycle_end_to_end():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))

    published = run_to_published(policy, "PROJECT", project["id"], requester, approver)
    assert published["status"] == "PUBLISHED"
    assert published["current_version_number"] == 1
    assert published["published_at"] is not None


def test_cannot_skip_review():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))

    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "skip review attempt",
        },
        headers=headers_for(str(requester.id)),
    )
    publication = response.json()

    # Publishing straight from DRAFT must fail.
    response = client.post(
        f"/api/v1/publications/{publication['id']}/publish",
        headers=headers_for(str(approver.id)),
    )
    assert response.status_code == 422, response.text


def test_requester_cannot_approve_own_request():
    supervisor = setup_user()
    assign(str(supervisor.id), "SUPERVISOR")
    project = api_create_project(str(supervisor.id))
    policy = create_policy(target_types=("PROJECT",))

    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "self approval attempt",
        },
        headers=headers_for(str(supervisor.id)),
    )
    publication = response.json()
    client.post(
        f"/api/v1/publications/{publication['id']}/submit-review",
        headers=headers_for(str(supervisor.id)),
    )
    response = client.post(
        f"/api/v1/publications/{publication['id']}/approve",
        headers=headers_for(str(supervisor.id)),
    )
    assert response.status_code == 422, response.text


def test_duplicate_publication_request_is_idempotent():
    requester = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))
    body = {
        "target_type": "PROJECT",
        "target_id": project["id"],
        "policy_id": policy["id"],
        "reason": "idempotency test",
    }
    first = client.post("/api/v1/publications", json=body, headers=headers_for(str(requester.id)))
    second = client.post("/api/v1/publications", json=body, headers=headers_for(str(requester.id)))
    assert first.status_code in (200, 201), first.text
    assert second.status_code in (200, 201), second.text
    assert first.json()["id"] == second.json()["id"]


# ---------------------------------------------------------------------------
# Public visibility (§17)
# ---------------------------------------------------------------------------


def test_published_project_is_publicly_retrievable():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id), name="Publicly visible bridge")
    policy = create_policy(target_types=("PROJECT",))
    published = run_to_published(policy, "PROJECT", project["id"], requester, approver)

    response = client.get(f"/api/v1/public/projects/{published['public_id']}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["public_id"] == published["public_id"]
    assert body["name"] == "Publicly visible bridge"


def test_unpublished_project_is_not_publicly_retrievable():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))

    # Create but never publish.
    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "never published",
        },
        headers=headers_for(str(requester.id)),
    )
    publication = response.json()
    response = client.get(f"/api/v1/public/projects/{publication['public_id']}")
    assert response.status_code == 404, response.text


def test_rejected_publication_is_not_publicly_retrievable():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))

    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "to be rejected",
        },
        headers=headers_for(str(requester.id)),
    )
    publication = response.json()
    client.post(
        f"/api/v1/publications/{publication['id']}/submit-review",
        headers=headers_for(str(requester.id)),
    )
    response = client.post(
        f"/api/v1/publications/{publication['id']}/reject",
        headers=headers_for(str(approver.id)),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REJECTED"

    response = client.get(f"/api/v1/public/projects/{publication['public_id']}")
    assert response.status_code == 404, response.text


def test_unpublish_removes_public_availability():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))
    published = run_to_published(policy, "PROJECT", project["id"], requester, approver)

    assert client.get(f"/api/v1/public/projects/{published['public_id']}").status_code == 200

    response = client.post(
        f"/api/v1/publications/{published['id']}/unpublish",
        headers=headers_for(str(approver.id)),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "UNPUBLISHED"
    assert client.get(f"/api/v1/public/projects/{published['public_id']}").status_code == 404


def test_public_project_listing_is_paginated():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    policy = create_policy(target_types=("PROJECT",))
    for index in range(2):
        project = api_create_project(str(requester.id), name=f"Listed project {index}")
        run_to_published(policy, "PROJECT", project["id"], requester, approver)

    response = client.get("/api/v1/public/projects?limit=1&offset=0")
    assert response.status_code == 200, response.text
    assert len(response.json()) <= 1

    # Oversized page is rejected rather than served unbounded.
    assert client.get("/api/v1/public/projects?limit=100000").status_code == 422


def test_public_endpoints_do_not_expose_internal_identifiers():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))
    published = run_to_published(policy, "PROJECT", project["id"], requester, approver)

    body = client.get(f"/api/v1/public/projects/{published['public_id']}").text
    # The internal UUID must never appear in a public payload.
    assert project["id"] not in body
    assert "storage_key" not in body
    assert "owner_id" not in body


def test_public_identifier_is_stable_across_access():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))
    published = run_to_published(policy, "PROJECT", project["id"], requester, approver)

    first = client.get(f"/api/v1/public/projects/{published['public_id']}").json()["public_id"]
    second = client.get(f"/api/v1/public/projects/{published['public_id']}").json()["public_id"]
    assert first == second == published["public_id"]
    assert published["public_id"].startswith("POA-PROJ-")


# ---------------------------------------------------------------------------
# Privacy (§19, §21, §22)
# ---------------------------------------------------------------------------


def test_public_evidence_never_leaks_storage_key_or_exif():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("EVIDENCE",))

    session = get_session()
    try:
        evidence = Evidence(
            filename="secret-photo.jpg",
            storage_key="quarantine/internal/secret-photo.jpg",
            content_type="image/jpeg",
            file_size=1234,
            status="analysis_complete",
            project_id=project["id"],
        )
        session.add(evidence)
        session.commit()
        session.refresh(evidence)
        session.add(
            EvidenceMetadata(
                evidence_id=evidence.id,
                metadata_json={"exif": {"gps": [18.5984, 73.7898]}},
            )
        )
        session.commit()
        evidence_id = str(evidence.id)
    finally:
        session.close()

    published = run_to_published(policy, "EVIDENCE", evidence_id, requester, approver)
    response = client.get(f"/api/v1/public/evidence/{published['public_id']}")
    assert response.status_code == 200, response.text
    body = response.text
    assert "quarantine/internal/secret-photo.jpg" not in body
    assert "storage_key" not in body
    assert "exif" not in body
    # GPS must be precision-reduced, not exact coordinates.
    assert "18.5984" not in body


def test_private_evidence_is_not_publishable():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("EVIDENCE",))

    session = get_session()
    try:
        evidence = Evidence(
            filename="private.jpg",
            storage_key="quarantine/private.jpg",
            status="private",
            file_size=1,
            project_id=project["id"],
        )
        session.add(evidence)
        session.commit()
        session.refresh(evidence)
        evidence_id = str(evidence.id)
    finally:
        session.close()

    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "EVIDENCE",
            "target_id": evidence_id,
            "policy_id": policy["id"],
            "reason": "private evidence attempt",
        },
        headers=headers_for(str(requester.id)),
    )
    publication = response.json()
    client.post(
        f"/api/v1/publications/{publication['id']}/submit-review",
        headers=headers_for(str(requester.id)),
    )
    response = client.post(
        f"/api/v1/publications/{publication['id']}/approve",
        headers=headers_for(str(approver.id)),
    )
    assert response.status_code == 422, response.text

    # Eligibility reports the structured reason rather than a generic denial.
    response = client.get(
        f"/api/v1/publications/{publication['id']}/eligibility",
        headers=headers_for(str(approver.id)),
    )
    codes = [b["code"] for b in response.json()["blockers"]]
    assert "PRIVATE_VISIBILITY" in codes


# ---------------------------------------------------------------------------
# Governance interactions (§12, §13)
# ---------------------------------------------------------------------------


def test_active_dispute_blocks_approval():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))

    session = get_session()
    try:
        session.add(
            Dispute(
                target_type="PROJECT",
                target_id=project["id"],
                project_id=project["id"],
                initiator_id=requester.id,
                reason="challenge before publication",
                status="OPEN",
            )
        )
        session.commit()
    finally:
        session.close()

    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "disputed target",
        },
        headers=headers_for(str(requester.id)),
    )
    publication = response.json()
    client.post(
        f"/api/v1/publications/{publication['id']}/submit-review",
        headers=headers_for(str(requester.id)),
    )
    response = client.post(
        f"/api/v1/publications/{publication['id']}/approve",
        headers=headers_for(str(approver.id)),
    )
    assert response.status_code == 422, response.text

    response = client.get(
        f"/api/v1/publications/{publication['id']}/eligibility",
        headers=headers_for(str(approver.id)),
    )
    codes = [b["code"] for b in response.json()["blockers"]]
    assert "ACTIVE_DISPUTE" in codes


def test_unresolved_correction_blocks_evidence_publication():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("EVIDENCE",))

    session = get_session()
    try:
        evidence = Evidence(
            filename="corrected.jpg",
            storage_key="quarantine/corrected.jpg",
            status="analysis_complete",
            file_size=1,
            project_id=project["id"],
        )
        session.add(evidence)
        session.commit()
        session.refresh(evidence)
        session.add(
            CorrectionRequest(
                target_type="EVIDENCE",
                target_id=evidence.id,
                project_id=project["id"],
                category="LOCATION_CONTEXT",
                requested_change={"location": "somewhere"},
                reason="pending correction",
                requester_id=requester.id,
                status="REQUESTED",
            )
        )
        session.commit()
        evidence_id = str(evidence.id)
    finally:
        session.close()

    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "EVIDENCE",
            "target_id": evidence_id,
            "policy_id": policy["id"],
            "reason": "pending correction",
        },
        headers=headers_for(str(requester.id)),
    )
    publication = response.json()
    client.post(
        f"/api/v1/publications/{publication['id']}/submit-review",
        headers=headers_for(str(requester.id)),
    )
    response = client.post(
        f"/api/v1/publications/{publication['id']}/approve",
        headers=headers_for(str(approver.id)),
    )
    assert response.status_code == 422, response.text

    response = client.get(
        f"/api/v1/publications/{publication['id']}/eligibility",
        headers=headers_for(str(approver.id)),
    )
    codes = [b["code"] for b in response.json()["blockers"]]
    assert "UNRESOLVED_CORRECTION" in codes


def test_legal_hold_is_reported_as_a_blocker():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("EVIDENCE",))

    session = get_session()
    try:
        evidence = Evidence(
            filename="held.jpg",
            storage_key="quarantine/held.jpg",
            status="analysis_complete",
            file_size=1,
            project_id=project["id"],
        )
        session.add(evidence)
        session.commit()
        session.refresh(evidence)
        evidence_id = str(evidence.id)
        session.add(
            RetentionHold(
                scope="RESOURCE",
                resource_type="EVIDENCE",
                resource_id=evidence.id,
                reason="litigation hold",
                status="ACTIVE",
            )
        )
        session.commit()
    finally:
        session.close()

    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "EVIDENCE",
            "target_id": evidence_id,
            "policy_id": policy["id"],
            "reason": "held evidence",
        },
        headers=headers_for(str(requester.id)),
    )
    publication = response.json()
    response = client.get(
        f"/api/v1/publications/{publication['id']}/eligibility",
        headers=headers_for(str(approver.id)),
    )
    codes = [b["code"] for b in response.json()["blockers"]]
    assert "LEGAL_HOLD" in codes


# ---------------------------------------------------------------------------
# Versioning + immutability (§7, §37)
# ---------------------------------------------------------------------------


def test_published_version_snapshot_is_immutable():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id), name="Original name")
    policy = create_policy(target_types=("PROJECT",))
    published = run_to_published(policy, "PROJECT", project["id"], requester, approver)

    session = get_session()
    try:
        version = (
            session.query(PublicationVersion)
            .filter(PublicationVersion.publication_id == published["id"])
            .one()
        )
        original_snapshot = dict(version.snapshot)
        assert original_snapshot["name"] == "Original name"

        # Mutate the internal source record.
        row = session.query(Project).filter(Project.id == project["id"]).one()
        row.name = "Mutated internal name"
        session.commit()

        session.expire_all()
        version = (
            session.query(PublicationVersion)
            .filter(PublicationVersion.publication_id == published["id"])
            .one()
        )
        # The published snapshot must NOT track the source mutation.
        assert version.snapshot["name"] == "Original name"
        assert version.snapshot == original_snapshot
    finally:
        session.close()


def test_version_ordering_and_current_resolution():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))
    published = run_to_published(policy, "PROJECT", project["id"], requester, approver)

    session = get_session()
    try:
        versions = (
            session.query(PublicationVersion)
            .filter(PublicationVersion.publication_id == published["id"])
            .order_by(PublicationVersion.version_number.asc())
            .all()
        )
        assert len(versions) == 1
        assert versions[0].version_number == 1
        assert versions[0].status == "PUBLISHED"

        container = session.query(Publication).filter(Publication.id == published["id"]).one()
        assert container.current_version_number == 1
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Audit + authorization (§26, §14)
# ---------------------------------------------------------------------------


def test_publication_mutations_emit_audit_events():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))
    published = run_to_published(policy, "PROJECT", project["id"], requester, approver)

    session = get_session()
    try:
        types = {
            row.event_type
            for row in session.query(AuditLedgerEvent)
            .filter(AuditLedgerEvent.resource_type == "publication")
            .filter(AuditLedgerEvent.resource_id == published["id"])
            .all()
        }
        for event in (
            "PUBLICATION_CREATED",
            "PUBLICATION_REVIEW_STARTED",
            "PUBLICATION_APPROVED",
            "PUBLICATION_PUBLISHED",
            "PUBLIC_PUBLICATION_VERSION_CREATED",
        ):
            assert event in types
    finally:
        session.close()


def test_publication_events_are_recorded():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))
    published = run_to_published(policy, "PROJECT", project["id"], requester, approver)

    session = get_session()
    try:
        events = (
            session.query(PublicationEvent)
            .filter(PublicationEvent.publication_id == published["id"])
            .order_by(PublicationEvent.created_at.asc())
            .all()
        )
        types = [event.event_type for event in events]
        assert types[0] == "CREATED"
        assert "APPROVED" in types
        assert "PUBLISHED" in types
    finally:
        session.close()


def test_read_requires_publication_permission():
    plain = setup_user()  # no roles
    requester = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))

    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "permission test",
        },
        headers=headers_for(str(requester.id)),
    )
    publication_id = response.json()["id"]

    response = client.get(
        f"/api/v1/publications/{publication_id}", headers=headers_for(str(plain.id))
    )
    assert response.status_code in (401, 403), response.text


def test_cross_project_isolation_blocks_publication_read():
    owner = setup_user()
    outsider = setup_user()
    assign(str(owner.id), "FIELD_OFFICER")
    project = api_create_project(str(owner.id))
    policy = create_policy(target_types=("PROJECT",))

    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "isolation test",
        },
        headers=headers_for(str(owner.id)),
    )
    publication_id = response.json()["id"]

    # An unrelated user with no scope must not read it.
    response = client.get(
        f"/api/v1/publications/{publication_id}", headers=headers_for(str(outsider.id))
    )
    assert response.status_code in (401, 403, 404), response.text


def test_public_identifier_is_not_derived_from_internal_uuid():
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))
    published = run_to_published(policy, "PROJECT", project["id"], requester, approver)

    assert published["public_id"] != project["id"]
    assert published["public_id"].startswith("POA-")
    # Not a raw UUID either.
    assert len(published["public_id"].split("-")) == 3
