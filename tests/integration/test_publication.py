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

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.db.models import (
    AuditLedgerEvent,
    CorrectionRequest,
    Dispute,
    Evidence,
    EvidenceMetadata,
    Project,
    Publication,
    PublicationEvent,
    PublicationPolicyVersion,
    PublicationVersion,
    RetentionHold,
    User,
)
from backend.db.session import get_session
from backend.services import authorization as auth_service


client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def seed_catalogue():
    """Seed the role/permission catalogue before every test in this module.

    Authentication resolves permissions from the ``role_permissions`` TABLE
    (via ``auth_repo.permissions_for_roles``), not from the
    ``AUTH_ROLE_PERMISSIONS`` constant. That table is populated by
    ``ensure_default_catalogue`` and, in a deployed database, by the baseline
    seed revision ``u1v2w3x4y031``, which inserts the same rows from the same
    constants. The fixture still calls the service directly so this module is
    correct on any test database, whether or not that revision has been
    applied to it.

    Without this fixture, ``assign(..., "FIELD_OFFICER")`` writes a valid
    assignment against a role that has no ``role_permissions`` rows, so
    ``resolve_user_principal`` returns an empty permission set and every
    authenticated request is denied with 403 NO_PERMISSION. Previously this
    module only passed by accident, when another test file had already seeded
    the same database in the same session.

    Mirrors the ``seed_catalogue`` fixture in ``test_authorization.py`` (BE-016).
    """
    session = get_session()
    try:
        auth_service.ensure_default_catalogue(session)
    finally:
        session.close()


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
# Authorization contract (§14, §15)
#
# Regression: every authenticated request returned 403 NO_PERMISSION. The role
# mapping in AUTH_ROLE_PERMISSIONS grants FIELD_OFFICER publication.create, but
# principal.permissions is built from the role_permissions TABLE via
# permissions_for_roles(), and that table is only populated by
# ensure_default_catalogue. This module did not call it, so FIELD_OFFICER
# resolved to an empty permission set.
# ---------------------------------------------------------------------------


def test_field_officer_principal_carries_the_publication_create_permission():
    """The resolved principal must actually hold publication.create.

    This asserts the authorization *contract* directly — independent of any
    endpoint — so a missing catalogue row is caught here rather than surfacing
    as an opaque 403 in a dozen unrelated tests.
    """
    user = setup_user()
    assign(str(user.id), "FIELD_OFFICER")
    session = get_session()
    try:
        principal = auth_service.resolve_user_principal(session, str(user.id))
    finally:
        session.close()

    assert principal.authenticated is True
    assert principal.principal_type == "USER"
    assert "publication.create" in principal.permissions, (
        "FIELD_OFFICER resolved without publication.create; the "
        "role_permissions catalogue was not seeded"
    )
    # §15: officers may request but must never approve or publish their own.
    for forbidden in ("publication.approve", "publication.publish", "publication.unpublish"):
        assert forbidden not in principal.permissions


def test_field_officer_can_create_a_publication_request():
    """End-to-end proof that the 403 is gone on POST /api/v1/publications."""
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
            "reason": "BE-022 authorization contract test",
        },
        headers=headers_for(str(requester.id)),
    )
    assert response.status_code in (200, 201), (
        f"expected the request to be authorized, got {response.status_code}: "
        f"{response.text}"
    )
    assert "id" in response.json()


# ---------------------------------------------------------------------------
# Submit-for-review authorization contract (§6, §15)
#
# DRAFT -> PENDING_REVIEW is the requester handing over their own work, so it
# is gated on publication.create plus an ownership check, NOT on
# publication.review (which belongs to whoever later adjudicates the request).
# Regression: the endpoint previously required publication.review, so a
# FIELD_OFFICER -- who creates requests but does not adjudicate them -- was
# refused with 403 when submitting their own request.
# ---------------------------------------------------------------------------


def test_requester_may_submit_their_own_request_for_review():
    """A FIELD_OFFICER creates a request and submits it for review."""
    requester = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))

    created = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "requester submits own request",
        },
        headers=headers_for(str(requester.id)),
    )
    assert created.status_code in (200, 201), created.text
    publication_id = created.json()["id"]

    submitted = client.post(
        f"/api/v1/publications/{publication_id}/submit-review",
        headers=headers_for(str(requester.id)),
    )
    assert submitted.status_code == 200, (
        f"requester must be able to submit their own request, got "
        f"{submitted.status_code}: {submitted.text}"
    )
    assert submitted.json()["status"] == "PENDING_REVIEW"


def test_non_requester_may_not_submit_someone_elses_request():
    """A second officer holds publication.create but cannot submit another's draft.

    The endpoint gate alone would let them through -- they legitimately hold
    the permission -- so this asserts the service-level ownership check that
    makes the handover safe.
    """
    requester = setup_user()
    other_officer = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(other_officer.id), "FIELD_OFFICER")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))

    created = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "owned by requester",
        },
        headers=headers_for(str(requester.id)),
    )
    assert created.status_code in (200, 201), created.text
    publication_id = created.json()["id"]

    stolen = client.post(
        f"/api/v1/publications/{publication_id}/submit-review",
        headers=headers_for(str(other_officer.id)),
    )
    assert stolen.status_code == 422, stolen.text
    assert "requester" in stolen.json()["detail"].lower()

    # The request must still be a DRAFT -- the attempt changed nothing.
    still = client.get(
        f"/api/v1/publications/{publication_id}",
        headers=headers_for(str(requester.id)),
    )
    assert still.json()["status"] == "DRAFT"


def test_citizen_may_not_submit_for_review():
    """Citizens hold no publication.create, so they cannot submit either."""
    requester = setup_user()
    citizen = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(citizen.id), "CITIZEN")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))

    created = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "citizen must not submit",
        },
        headers=headers_for(str(requester.id)),
    )
    assert created.status_code in (200, 201), created.text
    publication_id = created.json()["id"]

    denied = client.post(
        f"/api/v1/publications/{publication_id}/submit-review",
        headers=headers_for(str(citizen.id)),
    )
    assert denied.status_code == 403, denied.text


def test_requester_still_cannot_approve_their_own_request():
    """Submitting your own request must not grant approval authority (§15)."""
    requester = setup_user()
    assign(str(requester.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("PROJECT",))

    created = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "self-approval attempt",
        },
        headers=headers_for(str(requester.id)),
    )
    assert created.status_code in (200, 201), created.text
    publication_id = created.json()["id"]

    submitted = client.post(
        f"/api/v1/publications/{publication_id}/submit-review",
        headers=headers_for(str(requester.id)),
    )
    assert submitted.status_code == 200, submitted.text

    # A supervisor holds publication.approve, so this passes the endpoint gate
    # and must be refused by the separation-of-duties check in the service.
    approved = client.post(
        f"/api/v1/publications/{publication_id}/approve",
        headers=headers_for(str(requester.id)),
    )
    assert approved.status_code == 422, approved.text
    assert "separation of duties" in approved.json()["detail"].lower()


def test_citizen_is_still_denied_publication_create():
    """Seeding the catalogue must not widen authority (no silent fallback)."""
    citizen = setup_user()
    assign(str(citizen.id), "CITIZEN")
    # The project is created via the unauthenticated development bypass (no role
    # holds project.create except SUPERVISOR), so the 403 under test can only
    # come from publication.create -- not from an earlier authorization step.
    project = api_create_project(str(citizen.id))
    policy = create_policy(target_types=("PROJECT",))

    response = client.post(
        "/api/v1/publications",
        json={
            "target_type": "PROJECT",
            "target_id": project["id"],
            "policy_id": policy["id"],
            "reason": "citizen must not be able to publish",
        },
        headers=headers_for(str(citizen.id)),
    )
    assert response.status_code == 403, response.text


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


def test_created_policy_response_carries_the_active_version_fields():
    """A created policy must respond with the flattened policy + ACTIVE version.

    Regression: the create path used to return the bare ``PublicationPolicy``
    ORM row, so ``PublicationPolicyResponse`` failed validation on the 13 fields
    that live on ``PublicationPolicyVersion`` rather than on the policy. The
    service now projects through ``policy_view`` (§9).
    """
    user = setup_user()
    assign(str(user.id), "ADMINISTRATOR")
    policy = create_policy(
        target_types=("PROJECT",),
        public_fields=["public_id", "name"],
        prohibited_fields=["storage_key"],
        min_authorization_level="SUPERVISOR",
        required_approvals=2,
        require_separation_of_duties=False,
        location_precision="AREA",
        redaction_level="STRICT",
    )
    for field in (
        "id",
        "name",
        "version",
        "status",
        "allowed_target_types",
        "public_fields",
        "prohibited_fields",
        "allow_media_exposure",
        "allow_derived_intelligence",
        "allow_review_outcomes",
        "min_authorization_level",
        "required_approvals",
        "require_separation_of_duties",
        "location_precision",
        "redaction_level",
    ):
        assert field in policy, f"policy response missing {field!r}: {policy}"
    # The version-derived configuration must be the *active* one that was
    # requested, not a placeholder default.
    assert policy["status"] == "ACTIVE"
    assert policy["allowed_target_types"] == ["PROJECT"]
    assert policy["public_fields"] == ["public_id", "name"]
    assert policy["prohibited_fields"] == ["storage_key"]
    assert policy["min_authorization_level"] == "SUPERVISOR"
    assert policy["required_approvals"] == 2
    assert policy["require_separation_of_duties"] is False
    assert policy["location_precision"] == "AREA"
    assert policy["redaction_level"] == "STRICT"


def test_idempotent_policy_creation_returns_the_existing_active_version():
    """Re-submitting a policy name must still resolve the ACTIVE version.

    Regression risk: the idempotent path (created=False) is a separate return
    from the creation path and previously returned the bare policy row, so a
    retried admin request would have failed response validation while the first
    one succeeded.
    """
    user = setup_user()
    assign(str(user.id), "ADMINISTRATOR")
    name = f"be022-projection-{uuid4()}"
    body = {
        "name": name,
        "version": "2.0",
        "allowed_target_types": ["PROJECT"],
        "public_fields": ["public_id", "name"],
        "min_authorization_level": "SUPERVISOR",
        "required_approvals": 2,
        "redaction_level": "STRICT",
    }
    first = client.post("/api/v1/publications/policies", json=body)
    assert first.status_code in (200, 201), first.text
    assert first.json()["status"] == "ACTIVE"
    assert first.json()["version"] == "2.0"

    second = client.post("/api/v1/publications/policies", json=body)
    assert second.status_code in (200, 201), second.text
    existing = second.json()
    assert existing["id"] == first.json()["id"]
    # The idempotent response carries the same projection as the created one.
    assert existing["status"] == "ACTIVE"
    assert existing["version"] == "2.0"
    assert existing["allowed_target_types"] == ["PROJECT"]
    assert existing["min_authorization_level"] == "SUPERVISOR"
    assert existing["required_approvals"] == 2
    assert existing["redaction_level"] == "STRICT"

    # A GET of the same policy must agree with both create responses.
    fetched = client.get(f"/api/v1/publications/policies/{existing['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["version"] == "2.0"
    assert fetched.json()["status"] == "ACTIVE"


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
# Publication-policy scope boundary (acceptance register §8.2)
#
# ``PublicationPolicy`` has no project or organization column, so there is no
# per-project instance to authorize against: every policy is organization-wide
# configuration. The single-item read already resolved to a scope-less
# ``Resource("publication_policy")``, which only a GLOBAL assignment can cover,
# but the LIST checked only ``"publication.read" in principal.permissions`` and
# the CREATE used a resource-less ``require(...)`` — both of which a caller who
# holds the permission in one project satisfies. That asymmetry let a
# project-scoped officer enumerate every policy and let a project-scoped
# administrator write new ones. All three guards now demand GLOBAL scope.
# ---------------------------------------------------------------------------


def test_project_scoped_publication_read_cannot_list_policies():
    """Holding publication.read for ONE project must not enumerate all policies."""
    user = setup_user()
    project = api_create_project(str(user.id))
    assign(str(user.id), "FIELD_OFFICER", scope="PROJECT", scope_id=project["id"])
    session = get_session()
    try:
        principal = auth_service.resolve_user_principal(session, str(user.id))
    finally:
        session.close()
    assert "publication.read" in principal.permissions, (
        "precondition failed: the PROJECT-scope grant did not produce the "
        "permission, so the refusal below would prove nothing"
    )
    assert all(scope.scope_type != "GLOBAL"
               for scope in principal.permissions["publication.read"])

    response = client.get("/api/v1/publications/policies",
                          headers=headers_for(str(user.id)))
    assert response.status_code == 403, (
        f"project-scoped publication.read was allowed to list organization-wide "
        f"policies: {response.status_code} {response.text}"
    )


def test_global_publication_read_lists_the_policies_that_exist():
    """The GLOBAL holder still works, and the list is not silently empty."""
    user = setup_user()
    assign(str(user.id), "ADMINISTRATOR")  # scope defaults to GLOBAL
    policy = create_policy()

    response = client.get("/api/v1/publications/policies",
                          headers=headers_for(str(user.id)))
    assert response.status_code == 200, response.text
    body = response.json()
    assert policy["id"] in {row["id"] for row in body["items"]}, (
        "the authorized listing came back without the policy that was just "
        "created; an empty result would make the refusal test vacuous"
    )


def test_project_scoped_policy_manage_cannot_create_policy():
    """Writing policy configuration requires GLOBAL policy authority."""
    user = setup_user()
    project = api_create_project(str(user.id))
    assign(str(user.id), "ADMINISTRATOR", scope="PROJECT", scope_id=project["id"])
    session = get_session()
    try:
        principal = auth_service.resolve_user_principal(session, str(user.id))
    finally:
        session.close()
    assert "publication.policy.manage" in principal.permissions, (
        "precondition failed: the PROJECT-scope grant did not produce "
        "publication.policy.manage, so the refusal below would prove nothing"
    )

    response = client.post(
        "/api/v1/publications/policies",
        json={"name": f"cross-scope-{uuid4()}", "version": "1.0",
              "allowed_target_types": ["PROJECT"]},
        headers=headers_for(str(user.id)),
    )
    assert response.status_code == 403, (
        f"project-scoped publication.policy.manage was allowed to create an "
        f"organization-wide policy: {response.status_code} {response.text}"
    )


def test_global_policy_manage_can_create_policy():
    user = setup_user()
    assign(str(user.id), "ADMINISTRATOR")
    response = client.post(
        "/api/v1/publications/policies",
        json={"name": f"global-{uuid4()}", "version": "1.0",
              "allowed_target_types": ["PROJECT"]},
        headers=headers_for(str(user.id)),
    )
    assert response.status_code in (200, 201), response.text


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


def test_persisted_snapshot_is_json_safe_and_leak_free():
    """Regression: publishing EVIDENCE failed on datetime -> JSONB.

    ``publish_publication`` used to hand ``build_snapshot``'s output straight to
    ``publication_versions.snapshot`` as JSONB. The projection carries
    ``collected_at = row.created_at``, a Python datetime, and JSONB has no
    native temporal type, so the INSERT raised
    ``TypeError: Object of type datetime is not JSON serializable``.

    This asserts the contract on the row that was actually persisted, not just
    on the HTTP response: the value must be JSON-native, the timestamp must be
    deterministic ISO-8601, and the privacy guarantees must be intact.
    """
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("EVIDENCE",))

    session = get_session()
    try:
        evidence = Evidence(
            filename="snapshot-check.jpg",
            storage_key="quarantine/internal/snapshot-check.jpg",
            content_type="image/jpeg",
            file_size=99,
            status="analysis_complete",
            project_id=project["id"],
        )
        session.add(evidence)
        session.commit()
        session.refresh(evidence)
        evidence_id = str(evidence.id)
    finally:
        session.close()

    published = run_to_published(policy, "EVIDENCE", evidence_id, requester, approver)

    session = get_session()
    try:
        version = (
            session.query(PublicationVersion)
            .filter(PublicationVersion.publication_id == published["id"])
            .one()
        )
        snapshot = version.snapshot
        # (2) Deterministic JSON-compatible timestamp. Reaching this row at all
        # proves the INSERT succeeded; an explicit type check pins the format.
        assert isinstance(snapshot["collected_at"], str), snapshot
        # tz-aware ISO-8601, and the value is really the evidence's timestamp.
        assert snapshot["collected_at"].endswith("+00:00"), snapshot
        # Round-trips through the stdlib encoder with no custom ``default``,
        # which is precisely what the driver does.
        json.dumps(snapshot)
        # (3)(4)(5) No storage key, no EXIF, no internal identifiers.
        blob = json.dumps(snapshot)
        assert "storage_key" not in blob
        assert "quarantine/internal" not in blob
        assert "exif" not in blob
        assert evidence_id not in blob
        assert str(evidence_id) not in blob
        assert str(requester.id) not in blob
        assert str(approver.id) not in blob
        # The source_version_references JSONB column must be JSON-safe too.
        json.dumps(version.source_version_references)
    finally:
        session.close()


def test_snapshot_timestamp_is_a_faithful_deterministic_rendering():
    """§32: the stored timestamp is a lossless, canonical rendering.

    Determinism is not just "it is a string" -- it must encode the *same
    instant* as the source column, in UTC, so the frozen public record cannot
    drift from the evidence it describes. Key sorting is asserted separately at
    the unit level, where a second version is not needed (UNPUBLISHED is
    terminal and create_publication is idempotent per target, so a republish
    cannot legitimately produce a second version here).
    """
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("EVIDENCE",))

    session = get_session()
    try:
        evidence = Evidence(
            filename="stable.jpg",
            storage_key="quarantine/internal/stable.jpg",
            content_type="image/jpeg",
            file_size=10,
            status="analysis_complete",
            project_id=project["id"],
        )
        session.add(evidence)
        session.commit()
        session.refresh(evidence)
        evidence_id = str(evidence.id)
        source_created_at = evidence.created_at
    finally:
        session.close()

    published = run_to_published(policy, "EVIDENCE", evidence_id, requester, approver)

    session = get_session()
    try:
        version = (
            session.query(PublicationVersion)
            .filter(PublicationVersion.publication_id == published["id"])
            .one()
        )
        stored = version.snapshot["collected_at"]
    finally:
        session.close()

    # Round-trips back to the identical instant.
    assert datetime.fromisoformat(stored) == source_created_at
    # ...and is rendered in UTC, matching the BE-015 canonical form.
    assert stored == source_created_at.astimezone(timezone.utc).isoformat()




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
    """A live BE-021 dispute on the target blocks approval (§12).

    §12 is scoped to "if a published object becomes disputed" -- the dispute and
    the publication are about the SAME object. The target here must therefore
    lie in the intersection of the two vocabularies:

        DISPUTE_TARGET_TYPES      EVIDENCE, EVIDENCE_CLAIM_RELATIONSHIP, CLAIM,
                                  EXTERNAL_ASSERTION, FUSION_ASSESSMENT,
                                  REVIEW_CASE
        PUBLICATION_TARGET_TYPES  PROJECT, ACTIVITY, CLAIM, EVIDENCE,
                                  REVIEW_CASE, FUSION_ASSESSMENT

    A project is publishable but NOT disputable: BE-021 §5.1 enumerates six
    disputable targets and omits PROJECT, and that omission is enforced in four
    independent places (the DB CHECK constraint, the Pydantic enum, the
    ``DISPUTE_TARGET_TYPES`` constant, and the service's TARGET_TYPES check).
    This test previously opened a ``Dispute(target_type="PROJECT")`` directly
    through the ORM, bypassing the service-layer check and hitting the CHECK
    constraint. The database was right; the test was wrong. EVIDENCE is used
    because it is in both vocabularies, mirroring the sibling correction test.
    """
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("EVIDENCE",))

    session = get_session()
    try:
        evidence = Evidence(
            filename="disputed.jpg",
            storage_key="quarantine/internal/disputed.jpg",
            status="analysis_complete",
            file_size=1,
            project_id=project["id"],
        )
        session.add(evidence)
        session.commit()
        session.refresh(evidence)
        evidence_id = str(evidence.id)
        session.add(
            Dispute(
                target_type="EVIDENCE",
                target_id=evidence.id,
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
            "target_type": "EVIDENCE",
            "target_id": evidence_id,
            "policy_id": policy["id"],
            "reason": "disputed target",
        },
        headers=headers_for(str(requester.id)),
    )
    assert response.status_code in (200, 201), response.text
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


def test_a_resolved_dispute_no_longer_blocks_approval():
    """§12: a resolved dispute must not permanently freeze the target.

    This is the counterpart to the blocker test. Without it, a one-line change
    that widened the active-status filter to include RESOLVED would still pass
    every other test in this file.
    """
    requester = setup_user()
    approver = setup_user()
    assign(str(requester.id), "FIELD_OFFICER")
    assign(str(approver.id), "SUPERVISOR")
    project = api_create_project(str(requester.id))
    policy = create_policy(target_types=("EVIDENCE",))

    session = get_session()
    try:
        evidence = Evidence(
            filename="cleared.jpg",
            storage_key="quarantine/internal/cleared.jpg",
            status="analysis_complete",
            file_size=1,
            project_id=project["id"],
        )
        session.add(evidence)
        session.commit()
        session.refresh(evidence)
        evidence_id = str(evidence.id)
        now = datetime.now(timezone.utc)
        session.add(
            Dispute(
                target_type="EVIDENCE",
                target_id=evidence.id,
                project_id=project["id"],
                initiator_id=requester.id,
                reason="challenge, since settled",
                status="RESOLVED",
                resolution="UPHELD",
                resolution_rationale="challenge resolved on the record",
                resolved_by=str(approver.id),
                resolved_at=now,
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
            "reason": "dispute already resolved",
        },
        headers=headers_for(str(requester.id)),
    )
    assert response.status_code in (200, 201), response.text
    publication = response.json()
    client.post(
        f"/api/v1/publications/{publication['id']}/submit-review",
        headers=headers_for(str(requester.id)),
    )

    response = client.get(
        f"/api/v1/publications/{publication['id']}/eligibility",
        headers=headers_for(str(approver.id)),
    )
    assert response.status_code == 200, response.text
    codes = [b["code"] for b in response.json()["blockers"]]
    assert "ACTIVE_DISPUTE" not in codes


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


# ---------------------------------------------------------------------------
# Persisted actor identity boundary (regression)
#
# The development bypass used to fabricate the literal string "dev-user" as
# the acting principal, which PostgreSQL rejected because every BE-022 actor
# column is UUID-backed:
#     invalid input syntax for type uuid: "dev-user"
# ---------------------------------------------------------------------------


def test_anonymous_policy_creation_stores_null_actor_not_a_fabricated_uuid():
    """created_by is nullable: an anonymous actor is NULL, never 'dev-user'."""
    admin = setup_user()
    assign(str(admin.id), "ADMINISTRATOR")
    name = f"be022-anon-{uuid4()}"

    # Unauthenticated (development bypass) — must not 500 on a UUID cast.
    response = client.post(
        "/api/v1/publications/policies",
        json={"name": name, "version": "1.0", "allowed_target_types": ["PROJECT"]},
    )
    assert response.status_code in (200, 201), response.text
    policy_id = response.json()["id"]

    session = get_session()
    try:
        version = (
            session.query(PublicationPolicyVersion)
            .filter(PublicationPolicyVersion.policy_id == policy_id)
            .one()
        )
        # Anonymous actor is recorded as NULL, not a fabricated identity.
        assert version.created_by is None
    finally:
        session.close()


def test_authenticated_policy_creation_persists_the_real_user_uuid():
    """A real USER principal must still persist its own User UUID."""
    admin = setup_user()
    assign(str(admin.id), "ADMINISTRATOR")
    name = f"be022-auth-{uuid4()}"

    response = client.post(
        "/api/v1/publications/policies",
        json={"name": name, "version": "1.0", "allowed_target_types": ["PROJECT"]},
        headers=headers_for(str(admin.id)),
    )
    assert response.status_code in (200, 201), response.text
    policy_id = response.json()["id"]

    session = get_session()
    try:
        version = (
            session.query(PublicationPolicyVersion)
            .filter(PublicationPolicyVersion.policy_id == policy_id)
            .one()
        )
        assert str(version.created_by) == str(admin.id)
    finally:
        session.close()


def test_synthetic_actor_cannot_be_written_into_a_uuid_column():
    """A non-UUID actor identity is refused with 422, never persisted."""
    from backend.services import publication as publication_service

    for synthetic in ("dev-user", "system", "anonymous", "not-a-uuid"):
        try:
            publication_service._require_uuid(synthetic, "actor_id")
        except ValueError as error:
            assert "Invalid actor_id" in str(error)
        else:  # pragma: no cover - a regression would land here
            raise AssertionError(f"synthetic actor {synthetic!r} was accepted")


def test_unauthenticated_publication_request_is_rejected_not_crashed():
    """requested_by is NOT NULL: an unattributable actor gets 401, not a 500.

    Previously the development bypass invented "dev-user" and the request died
    inside PostgreSQL with InvalidTextRepresentation. It must now be refused
    cleanly at the identity boundary.
    """
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
            "reason": "unauthenticated attempt",
        },
    )
    # Rejected at the identity boundary - never a 500 from a UUID cast.
    assert response.status_code == 401, response.text
    assert "dev-user" not in response.text


def test_publication_request_persists_the_requesting_user_uuid():
    """A real USER principal persists its own UUID into requested_by."""
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
            "reason": "attribution test",
        },
        headers=headers_for(str(requester.id)),
    )
    assert response.status_code in (200, 201), response.text
    publication_id = response.json()["id"]

    session = get_session()
    try:
        publication = session.query(Publication).filter(Publication.id == publication_id).one()
        assert str(publication.requested_by) == str(requester.id)
    finally:
        session.close()
