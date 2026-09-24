"""BE-022 unit tests: policy rules, lifecycle, privacy, identifiers, and
bounded telemetry — pure logic only, no database (§38).

Covers the spec's explicit rules: lifecycle matrix (§6), target allowlist
(§4), prohibited-field detection (§5/§21), public identifier format (§16),
structured blockers (§11), and closed metric labels (§35).
"""

import pytest

from backend.db.models import (
    AUTH_PERMISSIONS,
    AUTH_ROLE_PERMISSIONS,
    AUDIT_EVENT_TYPES,
    NOTIFICATION_TYPES,
    PUBLICATION_BLOCKERS,
    PUBLICATION_INTERNALLY_PROHIBITED_FIELDS,
    PUBLICATION_STATUSES,
    PUBLICATION_TARGET_TYPES,
)
from backend.observability import publication_metrics
from backend.services import publication as publication_service
from backend.services.authorization import (
    ACTION_PERMISSIONS,
    PERMISSIONS,
    publication_target_resource,
)


# ---------------------------------------------------------------------------
# Lifecycle (§6)
# ---------------------------------------------------------------------------


def test_lifecycle_accepts_documented_moves():
    valid = [
        ("DRAFT", "PENDING_REVIEW"),
        ("PENDING_REVIEW", "APPROVED"),
        ("PENDING_REVIEW", "REJECTED"),
        ("APPROVED", "PUBLISHED"),
        ("APPROVED", "REJECTED"),
        ("PUBLISHED", "UNPUBLISHED"),
    ]
    for from_status, to_status in valid:
        publication_service.validate_transition(from_status, to_status)


def test_lifecycle_rejects_invalid_moves():
    invalid = [
        ("DRAFT", "PUBLISHED"),       # cannot skip review
        ("DRAFT", "APPROVED"),
        ("DRAFT", "REJECTED"),
        ("PENDING_REVIEW", "PUBLISHED"),  # must be approved first
        ("PENDING_REVIEW", "DRAFT"),
        ("APPROVED", "PENDING_REVIEW"),
        ("PUBLISHED", "DRAFT"),       # never silently return to editable
        ("PUBLISHED", "APPROVED"),
        ("PUBLISHED", "PENDING_REVIEW"),
        ("PUBLISHED", "PUBLISHED"),
        ("UNPUBLISHED", "PUBLISHED"),  # terminal
        ("REJECTED", "PUBLISHED"),     # terminal
    ]
    for from_status, to_status in invalid:
        with pytest.raises(ValueError):
            publication_service.validate_transition(from_status, to_status)


def test_terminal_states_have_no_exits():
    for terminal in ("UNPUBLISHED", "REJECTED"):
        assert publication_service.TRANSITIONS[terminal] == frozenset()


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError):
        publication_service.validate_transition("NOT_A_STATUS", "PUBLISHED")


# ---------------------------------------------------------------------------
# Target allowlist (§4)
# ---------------------------------------------------------------------------


def test_target_allowlist_is_explicit_and_closed():
    assert set(PUBLICATION_TARGET_TYPES) == {
        "PROJECT",
        "ACTIVITY",
        "CLAIM",
        "EVIDENCE",
        "REVIEW_CASE",
        "FUSION_ASSESSMENT",
    }


def test_internal_objects_are_not_publishable_targets():
    # Audit events, users, permissions, notifications and API clients are
    # never publishable (§4).
    for forbidden in ("USER", "AUDIT_EVENT", "PERMISSION", "API_CLIENT", "NOTIFICATION"):
        assert forbidden not in PUBLICATION_TARGET_TYPES


def test_publication_target_resource_maps_every_allowlisted_type():
    for target in PUBLICATION_TARGET_TYPES:
        assert publication_target_resource(target) is not None


def test_publication_target_resource_rejects_unknown():
    assert publication_target_resource("USER") is None
    assert publication_target_resource(None) is None
    assert publication_target_resource("") is None


# ---------------------------------------------------------------------------
# Privacy: prohibited fields (§5, §21)
# ---------------------------------------------------------------------------


def test_prohibited_field_set_covers_the_spec_list():
    for field in (
        "storage_key",
        "exif",
        "user_id",
        "reviewer_id",
        "secret",
        "password",
        "token",
        "priority_score",
        "fusion_signals",
    ):
        assert field in PUBLICATION_INTERNALLY_PROHIBITED_FIELDS


def test_assert_no_prohibited_fields_rejects_top_level_leak():
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._assert_no_prohibited_fields({"storage_key": "internal/path"})


def test_assert_no_prohibited_fields_rejects_nested_leak():
    payload = {"content": {"meta": {"exif": {"gps": 1}}}}
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._assert_no_prohibited_fields(payload)


def test_assert_no_prohibited_fields_rejects_list_leak():
    payload = {"items": [{"ok": 1}, {"token": "abc"}]}
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._assert_no_prohibited_fields(payload)


def test_assert_no_prohibited_fields_allows_clean_payload():
    publication_service._assert_no_prohibited_fields(
        {"public_id": "POA-PROJ-000001", "name": "Bridge project", "media": []}
    )


def test_private_visibility_values_are_never_public():
    for value in (
        "CITIZEN_OWNED_PRIVATE",
        "OPERATIONAL",
        "INTELLIGENCE_INTERNAL",
        "ADMINISTRATIVE_SECURITY",
    ):
        assert value in publication_service.PRIVATE_VISIBILITY_VALUES
    assert "PUBLIC" not in publication_service.PRIVATE_VISIBILITY_VALUES


# ---------------------------------------------------------------------------
# Public identifiers (§16)
# ---------------------------------------------------------------------------


def test_public_id_prefixes_cover_every_target_type():
    for target in PUBLICATION_TARGET_TYPES:
        assert target in publication_service.PUBLIC_ID_PREFIXES


def test_public_ids_are_non_sensitive_and_namespaced():
    # A public id is a namespaced sequential token, never a UUID or secret.
    assert publication_service.PUBLIC_ID_PREFIXES["PROJECT"] == "PROJ"
    assert publication_service.PUBLIC_ID_PREFIXES["EVIDENCE"] == "EVD"
    for prefix in publication_service.PUBLIC_ID_PREFIXES.values():
        assert "-" not in prefix
        assert prefix.isupper()


# ---------------------------------------------------------------------------
# Blockers (§11)
# ---------------------------------------------------------------------------


def test_blockers_are_structured_not_collapsed():
    assert len(PUBLICATION_BLOCKERS) >= 10
    assert "NOT_ALLOWED" not in PUBLICATION_BLOCKERS
    for code in (
        "UNAUTHORIZED",
        "NOT_PUBLISHABLE_TYPE",
        "PRIVATE_VISIBILITY",
        "ACTIVE_DISPUTE",
        "UNRESOLVED_CORRECTION",
        "RETENTION_RESTRICTION",
        "LEGAL_HOLD",
        "MISSING_REQUIRED_APPROVAL",
        "SENSITIVE_DATA_PRESENT",
        "SOURCE_RESTRICTION",
        "UNAVAILABLE_PUBLIC_DERIVATIVE",
    ):
        assert code in PUBLICATION_BLOCKERS


# ---------------------------------------------------------------------------
# Authorization (§14)
# ---------------------------------------------------------------------------


def test_publication_permissions_are_registered():
    for permission in (
        "publication.create",
        "publication.read",
        "publication.review",
        "publication.approve",
        "publication.publish",
        "publication.unpublish",
        "publication.policy.manage",
    ):
        assert permission in AUTH_PERMISSIONS
        assert permission in PERMISSIONS
        assert ACTION_PERMISSIONS[permission] == permission


def test_administrators_do_not_receive_substantive_publication_authority():
    admin = set(AUTH_ROLE_PERMISSIONS["ADMINISTRATOR"])
    for substantive in (
        "publication.create",
        "publication.review",
        "publication.approve",
        "publication.publish",
        "publication.unpublish",
    ):
        assert substantive not in admin
    # Policy management stays administrative and read stays available.
    assert "publication.policy.manage" in admin
    assert "publication.read" in admin


def test_supervisor_holds_the_substantive_publication_actions():
    supervisor = set(AUTH_ROLE_PERMISSIONS["SUPERVISOR"])
    for action in (
        "publication.approve",
        "publication.publish",
        "publication.unpublish",
    ):
        assert action in supervisor
    # But not administrative policy management (§14).
    assert "publication.policy.manage" not in supervisor


def test_reviewer_cannot_approve_or_publish():
    reviewer = set(AUTH_ROLE_PERMISSIONS["REVIEWER"])
    assert "publication.review" in reviewer
    assert "publication.approve" not in reviewer
    assert "publication.publish" not in reviewer


def test_citizens_have_no_publication_authority():
    citizen = set(AUTH_ROLE_PERMISSIONS["CITIZEN"])
    for permission in (
        "publication.create",
        "publication.approve",
        "publication.publish",
        "publication.unpublish",
    ):
        assert permission not in citizen


def test_role_permission_mappings_only_use_known_permissions():
    for role, permissions in AUTH_ROLE_PERMISSIONS.items():
        for permission in permissions:
            assert permission in AUTH_PERMISSIONS, f"{role} -> {permission}"


# ---------------------------------------------------------------------------
# Audit + notification vocabulary (§26, §27)
# ---------------------------------------------------------------------------


def test_required_audit_events_are_registered():
    for event in (
        "PUBLICATION_CREATED",
        "PUBLICATION_REVIEW_STARTED",
        "PUBLICATION_APPROVED",
        "PUBLICATION_REJECTED",
        "PUBLICATION_PUBLISHED",
        "PUBLICATION_UNPUBLISHED",
        "PUBLICATION_POLICY_CREATED",
        "PUBLICATION_POLICY_UPDATED",
        "PUBLICATION_ELIGIBILITY_FAILED",
        "PUBLIC_PUBLICATION_VERSION_CREATED",
    ):
        assert event in AUDIT_EVENT_TYPES


def test_publication_notification_types_are_registered():
    for notification in (
        "PUBLICATION_SUBMITTED",
        "PUBLICATION_APPROVED",
        "PUBLICATION_REJECTED",
        "PUBLICATION_PUBLISHED",
        "PUBLICATION_UNPUBLISHED",
        "PUBLICATION_REQUIRES_REVIEW",
    ):
        assert notification in NOTIFICATION_TYPES


# ---------------------------------------------------------------------------
# Bounded telemetry labels (§35)
# ---------------------------------------------------------------------------


def test_metric_label_vocabularies_are_closed():
    assert set(publication_metrics.TARGET_TYPES) == set(PUBLICATION_TARGET_TYPES)
    assert set(publication_metrics.PUBLICATION_STATUSES) == set(PUBLICATION_STATUSES)
    assert set(publication_metrics.BLOCKERS) == set(PUBLICATION_BLOCKERS)


def test_high_cardinality_labels_are_forbidden():
    # §35 explicitly forbids these as Prometheus labels.
    forbidden = {"user_id", "project_id", "evidence_id", "claim_id", "publication_id", "public_id"}
    for vocabulary in (
        publication_metrics.TARGET_TYPES,
        publication_metrics.PUBLICATION_STATUSES,
        publication_metrics.BLOCKERS,
    ):
        assert not (set(vocabulary) & forbidden)


def test_unknown_label_values_are_coerced_to_bounded_fallbacks():
    # A high-cardinality or unexpected value must not become a label.
    assert publication_metrics._bounded("NOT_A_TYPE", publication_metrics.TARGET_TYPES, "PROJECT") == "PROJECT"
    assert publication_metrics._bounded(
        "public_id_abc123", publication_metrics.BLOCKERS, "SOURCE_RESTRICTION"
    ) == "SOURCE_RESTRICTION"
    # A legitimate value passes through unchanged.
    assert publication_metrics._bounded("EVIDENCE", publication_metrics.TARGET_TYPES, "PROJECT") == "EVIDENCE"
