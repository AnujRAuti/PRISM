"""BE-021 unit tests: vocabularies, lifecycles, staleness policy, and
traversal bounds — pure service logic only, no database (§35).

Every test here exercises explicit governance rules from the spec:
resolution vocabulary (§7), lifecycle matrices (§6, §10), staleness
semantics (§14), bounded traversal (§16), correction change validation
(§10), evidence immutability vocabulary, closed metric labels (§33), and
audit/notification vocabulary membership (§23, §24).
"""

import pytest

from backend.db.models import AUDIT_EVENT_TYPES
from backend.observability import governance_metrics
from backend.services import correction as correction_service
from backend.services import dispute as dispute_service
from backend.services import governance as governance_service
from backend.services.authorization import governance_target_resource


# ---------------------------------------------------------------------------
# Dispute lifecycle (§6)
# ---------------------------------------------------------------------------


def test_dispute_lifecycle_matrix_accepts_documented_moves():
    valid = [
        ("OPEN", "UNDER_REVIEW"), ("OPEN", "RESOLVED"), ("OPEN", "REJECTED"),
        ("OPEN", "ESCALATED"), ("OPEN", "WITHDRAWN"),
        ("UNDER_REVIEW", "RESOLVED"), ("UNDER_REVIEW", "REJECTED"),
        ("UNDER_REVIEW", "ESCALATED"), ("UNDER_REVIEW", "WITHDRAWN"),
        ("ESCALATED", "UNDER_REVIEW"),
    ]
    for from_status, to_status in valid:
        dispute_service.validate_transition(from_status, to_status)


def test_dispute_lifecycle_matrix_rejects_everything_else():
    invalid = [
        ("OPEN", "OPEN"),
        ("UNDER_REVIEW", "UNDER_REVIEW"), ("UNDER_REVIEW", "OPEN"),
        ("ESCALATED", "OPEN"), ("ESCALATED", "ESCALATED"),
        ("ESCALATED", "RESOLVED"), ("ESCALATED", "REJECTED"),
        ("ESCALATED", "WITHDRAWN"),
        ("RESOLVED", "OPEN"), ("RESOLVED", "UNDER_REVIEW"),
        ("RESOLVED", "ESCALATED"), ("RESOLVED", "RESOLVED"),
        ("RESOLVED", "REJECTED"), ("RESOLVED", "WITHDRAWN"),
        ("REJECTED", "OPEN"), ("REJECTED", "UNDER_REVIEW"),
        ("REJECTED", "RESOLVED"), ("REJECTED", "REJECTED"),
        ("WITHDRAWN", "OPEN"), ("WITHDRAWN", "RESOLVED"),
        ("WITHDRAWN", "WITHDRAWN"),
    ]
    for from_status, to_status in invalid:
        with pytest.raises(ValueError):
            dispute_service.validate_transition(from_status, to_status)


def test_dispute_terminal_states_have_no_exits():
    for terminal in ("RESOLVED", "REJECTED", "WITHDRAWN"):
        assert dispute_service.TRANSITIONS[terminal] == frozenset()
    # Escalation may only return to review (§6).
    assert dispute_service.TRANSITIONS["ESCALATED"] == frozenset({"UNDER_REVIEW"})
    assert dispute_service.ACTIVE_STATUSES == frozenset(
        {"OPEN", "UNDER_REVIEW", "ESCALATED"}
    )


def test_dispute_unknown_status_rejected():
    with pytest.raises(ValueError):
        dispute_service.validate_transition("UNKNOWN", "OPEN")
    with pytest.raises(ValueError):
        dispute_service.validate_transition("OPEN", "UNKNOWN")


# ---------------------------------------------------------------------------
# Resolution vocabulary (§7)
# ---------------------------------------------------------------------------


def test_resolution_vocabulary_is_exactly_the_specified_set():
    assert dispute_service.RESOLUTIONS == frozenset(
        {"UPHELD", "REJECTED", "INCONCLUSIVE", "INSUFFICIENT_EVIDENCE"}
    )


@pytest.mark.parametrize(
    "forbidden",
    ["FRAUD", "AUTHENTIC", "FAKE", "TRUE", "FALSE", "VALID", "GENUINE", "DEBUNKED"],
)
def test_resolution_vocabulary_never_determines_truth(forbidden):
    # A dispute resolution is a governance decision, never a truth verdict
    # about the underlying evidence (§7).
    assert forbidden not in dispute_service.RESOLUTIONS


# ---------------------------------------------------------------------------
# Dispute creation validation (§7, §35 "creation")
# ---------------------------------------------------------------------------


def test_create_dispute_rejects_unknown_target_type_without_db():
    with pytest.raises(ValueError, match="target type"):
        dispute_service.create_dispute(
            None,
            target_type="PLANET",
            target_id="00000000-0000-0000-0000-000000000001",
            initiator_id="00000000-0000-0000-0000-000000000002",
            reason="bad target",
        )


def test_create_dispute_rejects_bad_uuids_without_db():
    good = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(ValueError, match="target_id"):
        dispute_service.create_dispute(
            None, target_type="EVIDENCE", target_id="not-a-uuid",
            initiator_id=good, reason="x",
        )
    with pytest.raises(ValueError, match="initiator"):
        dispute_service.create_dispute(
            None, target_type="EVIDENCE", target_id=good,
            initiator_id="not-a-uuid", reason="x",
        )


def test_create_dispute_rejects_blank_and_oversized_reason():
    good = "00000000-0000-0000-0000-000000000001"
    for bad_reason in (None, "", "   "):
        with pytest.raises(ValueError, match="[Rr]eason"):
            dispute_service.create_dispute(
                None, target_type="EVIDENCE", target_id=good,
                initiator_id=good, reason=bad_reason,
            )
    with pytest.raises(ValueError, match="256"):
        dispute_service.create_dispute(
            None, target_type="EVIDENCE", target_id=good,
            initiator_id=good, reason="r" * 257,
        )


def test_resolve_target_rejects_unknown_type_and_bad_uuid():
    with pytest.raises(ValueError, match="target type"):
        dispute_service.resolve_target(None, "PLANET", "00000000-0000-0000-0000-000000000001")
    with pytest.raises(ValueError, match="target_id"):
        dispute_service.resolve_target(None, "EVIDENCE", "not-a-uuid")


# ---------------------------------------------------------------------------
# Correction lifecycle (§10)
# ---------------------------------------------------------------------------


def test_correction_lifecycle_matrix_accepts_documented_moves():
    valid = [
        ("REQUESTED", "UNDER_REVIEW"), ("REQUESTED", "APPROVED"),
        ("REQUESTED", "REJECTED"), ("REQUESTED", "CANCELLED"),
        ("UNDER_REVIEW", "APPROVED"), ("UNDER_REVIEW", "REJECTED"),
        ("UNDER_REVIEW", "CANCELLED"),
        ("APPROVED", "APPLIED"), ("APPROVED", "CANCELLED"),
    ]
    for from_status, to_status in valid:
        correction_service.validate_transition(from_status, to_status)


def test_correction_lifecycle_matrix_rejects_everything_else():
    invalid = [
        ("REQUESTED", "REQUESTED"), ("REQUESTED", "APPLIED"),
        ("UNDER_REVIEW", "UNDER_REVIEW"), ("UNDER_REVIEW", "REQUESTED"),
        ("UNDER_REVIEW", "APPLIED"),
        ("APPROVED", "UNDER_REVIEW"), ("APPROVED", "APPROVED"),
        ("APPROVED", "REJECTED"), ("APPROVED", "REQUESTED"),
        ("APPLIED", "APPLIED"), ("APPLIED", "CANCELLED"),
        ("APPLIED", "REQUESTED"), ("APPLIED", "APPROVED"),
        ("REJECTED", "REJECTED"), ("REJECTED", "APPROVED"),
        ("REJECTED", "CANCELLED"), ("REJECTED", "REQUESTED"),
        ("CANCELLED", "CANCELLED"), ("CANCELLED", "APPROVED"),
        ("CANCELLED", "APPLIED"), ("CANCELLED", "REQUESTED"),
    ]
    for from_status, to_status in invalid:
        with pytest.raises(ValueError):
            correction_service.validate_transition(from_status, to_status)


def test_correction_approval_and_application_are_distinct_states():
    # §10: approval and application are distinct steps.
    assert "APPLIED" not in correction_service.TRANSITIONS["REQUESTED"]
    assert "APPLIED" not in correction_service.TRANSITIONS["UNDER_REVIEW"]
    assert "APPLIED" in correction_service.TRANSITIONS["APPROVED"]


# ---------------------------------------------------------------------------
# Correction change validation (§10; pure categories only)
# ---------------------------------------------------------------------------


def test_location_change_requires_numeric_bounds():
    good = {"latitude": 12.34, "longitude": 56.78}
    assert correction_service.validate_requested_change(
        None, "EVIDENCE", "LOCATION_CONTEXT", good
    ) == {"latitude": 12.34, "longitude": 56.78}
    for bad in (
        {"latitude": 91.0, "longitude": 0.0},
        {"latitude": -91.0, "longitude": 0.0},
        {"latitude": 0.0, "longitude": 181.0},
        {"latitude": 0.0, "longitude": -181.0},
        {"latitude": "north", "longitude": 0.0},
        {"latitude": 0.0},
        {},
    ):
        with pytest.raises(ValueError):
            correction_service.validate_requested_change(
                None, "EVIDENCE", "LOCATION_CONTEXT", bad
            )


def test_descriptive_field_change_is_exactly_filename():
    assert correction_service.validate_requested_change(
        None, "EVIDENCE", "DESCRIPTIVE_FIELD", {"filename": "  photo.jpg "}
    ) == {"filename": "photo.jpg"}
    for bad in ({"filename": ""}, {"filename": "   "}, {"filename": "x" * 513},
                {"filename": 123}, {"other": "field"}, {}):
        with pytest.raises(ValueError):
            correction_service.validate_requested_change(
                None, "EVIDENCE", "DESCRIPTIVE_FIELD", bad
            )


def test_contextual_metadata_change_requires_non_empty_object():
    assert correction_service.validate_requested_change(
        None, "EVIDENCE", "CONTEXTUAL_METADATA", {"metadata": {"device": "A"}}
    ) == {"metadata": {"device": "A"}}
    for bad in ({"metadata": None}, {"metadata": {}}, {"metadata": "text"}, {}):
        with pytest.raises(ValueError):
            correction_service.validate_requested_change(
                None, "EVIDENCE", "CONTEXTUAL_METADATA", bad
            )


def test_association_changes_require_exact_keys():
    # UUID normalization happens before any database lookup, so malformed
    # values fail fast without a session.
    with pytest.raises(ValueError):
        correction_service.validate_requested_change(
            None, "EVIDENCE", "PROJECT_ASSOCIATION", {"project_id": "nope"}
        )
    with pytest.raises(ValueError):
        correction_service.validate_requested_change(
            None, "EVIDENCE", "PROJECT_ASSOCIATION", {"project_id": "x", "extra": 1}
        )
    with pytest.raises(ValueError):
        correction_service.validate_requested_change(
            None, "EVIDENCE", "CLAIM_ASSOCIATION", {}
        )


def test_evidence_file_change_cannot_reference_itself():
    target = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(ValueError, match="differ"):
        correction_service.validate_requested_change(
            None, target, "EVIDENCE_FILE", {"new_evidence_id": target}
        )
    with pytest.raises(ValueError):
        correction_service.validate_requested_change(
            None, target, "EVIDENCE_FILE", {"new_evidence_id": "bad", "x": 1}
        )


def test_unknown_category_and_empty_changes_rejected():
    with pytest.raises(ValueError):
        correction_service.validate_requested_change(
            None, "EVIDENCE", "MYSTERY", {"x": 1}
        )
    with pytest.raises(ValueError):
        correction_service.validate_requested_change(None, "EVIDENCE", "LOCATION_CONTEXT", {})
    with pytest.raises(ValueError):
        correction_service.validate_requested_change(None, "EVIDENCE", "LOCATION_CONTEXT", None)


# ---------------------------------------------------------------------------
# Staleness semantics (§14)
# ---------------------------------------------------------------------------


def test_staleness_policy_is_deterministic_by_cause():
    # Disputes invalidate outright; evidence-file replacements supersede;
    # context corrections and direct invalidations mark stale (§14).
    assert governance_service.staleness_for_cause("DISPUTE") == "INVALIDATED"
    assert (
        governance_service.staleness_for_cause("CORRECTION", "EVIDENCE_FILE")
        == "SUPERSEDED"
    )
    assert governance_service.staleness_for_cause("CORRECTION", "LOCATION_CONTEXT") == "STALE"
    assert governance_service.staleness_for_cause("CORRECTION", None) == "STALE"
    assert governance_service.staleness_for_cause("DIRECT") == "STALE"


def test_unknown_invalidation_cause_is_rejected_at_the_service_boundary():
    # The cause vocabulary is gated by the service entrypoint (invalidate_target),
    # not by the pure staleness mapping. staleness_for_cause is deliberately
    # total: it maps any input to a declared state so that an unvetted cause
    # can never produce a value outside STALENESS_STATES.
    target = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(ValueError, match="cause"):
        governance_service.invalidate_target(
            None,
            target_type="EVIDENCE",
            target_id=target,
            cause="VIBES",
            reason="unknown cause must be rejected",
            invalidated_by=target,
        )
    # The mapping stays total and inside the declared vocabulary.
    assert governance_service.staleness_for_cause("VIBES") in (
        governance_service.STALENESS_STATES
    )


def test_staleness_values_stay_within_declared_vocabulary():
    allowed = {"CURRENT", "STALE", "INVALIDATED", "SUPERSEDED"}
    values = {
        governance_service.staleness_for_cause("DISPUTE"),
        governance_service.staleness_for_cause("CORRECTION", "EVIDENCE_FILE"),
        governance_service.staleness_for_cause("CORRECTION", "DESCRIPTIVE_FIELD"),
        governance_service.staleness_for_cause("DIRECT"),
    }
    assert values <= allowed


# ---------------------------------------------------------------------------
# Bounded traversal (§16)
# ---------------------------------------------------------------------------


def test_traversal_bounds_are_finite_and_enforced():
    assert governance_service.MAX_TRAVERSAL_DEPTH == 10
    assert governance_service.MAX_TRAVERSAL_NODES == 1000
    # Bounds are validated before any database access.
    with pytest.raises(ValueError, match="target type"):
        governance_service.discover_dependencies(
            None, "PLANET", "00000000-0000-0000-0000-000000000001"
        )
    with pytest.raises(ValueError, match="max_depth"):
        governance_service.discover_dependencies(
            None, "EVIDENCE", "00000000-0000-0000-0000-000000000001", max_depth=0
        )
    with pytest.raises(ValueError, match="max_depth"):
        governance_service.discover_dependencies(
            None, "EVIDENCE", "00000000-0000-0000-0000-000000000001",
            max_depth=governance_service.MAX_TRAVERSAL_DEPTH + 1,
        )
    with pytest.raises(ValueError, match="max_nodes"):
        governance_service.discover_dependencies(
            None, "EVIDENCE", "00000000-0000-0000-0000-000000000001", max_nodes=0
        )
    with pytest.raises(ValueError, match="max_nodes"):
        governance_service.discover_dependencies(
            None, "EVIDENCE", "00000000-0000-0000-0000-000000000001",
            max_nodes=governance_service.MAX_TRAVERSAL_NODES + 1,
        )


def test_id_cap_for_audit_payloads():
    ids = [str(i).rjust(4, "0") for i in range(120)]
    capped = governance_service._capped(ids, 50)
    assert len(capped) == 50
    assert capped[0] == "0000"
    assert governance_service._capped([], 50) == []


# ---------------------------------------------------------------------------
# Invalidation / reprocessing input validation (§13, §17)
# ---------------------------------------------------------------------------


def test_invalidate_target_requires_actor_and_valid_cause():
    kwargs = {
        "target_type": "EVIDENCE",
        "target_id": "00000000-0000-0000-0000-000000000001",
        "reason": "governance decision",
    }
    with pytest.raises(ValueError, match="cause"):
        governance_service.invalidate_target(
            None, cause="GUT", invalidated_by="00000000-0000-0000-0000-000000000002", **kwargs
        )
    with pytest.raises(ValueError, match="[Rr]eason"):
        governance_service.invalidate_target(
            None, cause="DIRECT", invalidated_by="00000000-0000-0000-0000-000000000002",
            target_type="EVIDENCE", target_id="00000000-0000-0000-0000-000000000001",
            reason="  ",
        )
    with pytest.raises(ValueError, match="invalidated_by"):
        # invalidated_by must be passed explicitly: it is a required keyword-only
        # parameter, so omitting it would raise TypeError before validation runs.
        # The guard under test is the explicit None check.
        governance_service.invalidate_target(
            None, cause="DIRECT", invalidated_by=None,
            target_type="EVIDENCE", target_id="00000000-0000-0000-0000-000000000001",
            reason="governance decision",
        )


def test_request_reprocessing_requires_actor_reason_and_uuid():
    good = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(ValueError, match="evidence_id"):
        governance_service.request_reprocessing(
            None, evidence_id="nope", requested_by=good, reason="redo"
        )
    with pytest.raises(ValueError, match="requested_by"):
        governance_service.request_reprocessing(
            None, evidence_id=good, requested_by=None, reason="redo"
        )
    with pytest.raises(ValueError, match="[Rr]eason"):
        governance_service.request_reprocessing(
            None, evidence_id=good, requested_by=good, reason="   "
        )


def test_complete_reprocessing_requires_an_identifier():
    with pytest.raises(ValueError, match="reprocessing_id or analysis_job_id"):
        governance_service.complete_reprocessing(None)


# ---------------------------------------------------------------------------
# Authorization vocabulary (§11)
# ---------------------------------------------------------------------------


def test_every_dispute_target_type_resolves_to_a_scoped_resource():
    expected = {
        "EVIDENCE": "evidence",
        "CLAIM": "claim",
        "REVIEW_CASE": "review_case",
        "EVIDENCE_CLAIM_RELATIONSHIP": "graph_relationship",
        "FUSION_ASSESSMENT": "integrity_assessment",
        "EXTERNAL_ASSERTION": "external_assertion",
    }
    for target_type, resource_type in expected.items():
        assert governance_target_resource(target_type) == resource_type
    # Unknown types stay unresolvable (fail-closed), never silently scoped.
    assert governance_target_resource("PLANET") is None
    assert governance_target_resource(None) is None


# ---------------------------------------------------------------------------
# Audit / notification vocabulary membership (§23, §24)
# ---------------------------------------------------------------------------


def test_dispute_audit_types_are_registered_events():
    for audit_type in dispute_service.DISPUTE_AUDIT_TYPES.values():
        assert audit_type in AUDIT_EVENT_TYPES, audit_type


def test_correction_audit_types_are_registered_events():
    for audit_type in correction_service.CORRECTION_AUDIT_TYPES.values():
        assert audit_type in AUDIT_EVENT_TYPES, audit_type


def test_governance_audit_types_are_registered_events():
    # The governance service emits audit twins with inline event types;
    # every BE-021 type it can emit must be a registered ledger event.
    emitted = {
        "DEPENDENT_INTELLIGENCE_CHANGED",
        "GRAPH_RELATIONSHIP_INVALIDATED",
        "INTELLIGENCE_INVALIDATED",
        "INTELLIGENCE_REPROCESS_REQUESTED",
        "INTELLIGENCE_REPROCESS_FAILED",
        "INTELLIGENCE_REPROCESS_COMPLETED",
    }
    for audit_type in emitted:
        assert audit_type in AUDIT_EVENT_TYPES, audit_type


def test_be021_audit_events_registered_in_ledger():
    expected = {
        "DISPUTE_CREATED", "DISPUTE_ASSIGNED", "DISPUTE_REVIEW_STARTED",
        "DISPUTE_ESCALATED", "DISPUTE_RESOLVED", "DISPUTE_REJECTED",
        "DISPUTE_WITHDRAWN",
        "CORRECTION_REQUESTED", "CORRECTION_REVIEW_STARTED", "CORRECTION_APPROVED",
        "CORRECTION_REJECTED", "CORRECTION_APPLIED", "CORRECTION_CANCELLED",
        "INTELLIGENCE_INVALIDATED", "GRAPH_RELATIONSHIP_INVALIDATED",
        "INTELLIGENCE_REPROCESS_REQUESTED", "INTELLIGENCE_REPROCESS_COMPLETED",
        "INTELLIGENCE_REPROCESS_FAILED",
        "DEPENDENT_INTELLIGENCE_CHANGED",
    }
    assert expected <= AUDIT_EVENT_TYPES


def test_be021_notification_types_registered():
    from backend.db.models import NOTIFICATION_TYPES

    expected = {
        "DISPUTE_CREATED", "DISPUTE_ASSIGNED", "DISPUTE_ESCALATED",
        "DISPUTE_RESOLVED", "CORRECTION_APPROVED", "CORRECTION_REJECTED",
        "CORRECTION_APPLIED", "INTELLIGENCE_INVALIDATED",
        "REPROCESSING_COMPLETED",
    }
    assert expected <= set(NOTIFICATION_TYPES)
    for notif_type in dispute_service.DISPUTE_NOTIFICATION_TYPES.values():
        assert notif_type in NOTIFICATION_TYPES, notif_type
    for notif_type in correction_service.CORRECTION_NOTIFICATION_TYPES.values():
        assert notif_type in NOTIFICATION_TYPES, notif_type


def test_dispute_event_types_carry_both_audit_and_domain_semantics():
    # Every domain event maps to a registered audit type.
    assert set(dispute_service.DISPUTE_AUDIT_TYPES) == {
        "CREATED", "ASSIGNED", "REVIEW_STARTED", "ESCALATED",
        "RESOLVED", "REJECTED", "WITHDRAWN",
    }
    assert set(correction_service.CORRECTION_AUDIT_TYPES) == {
        "REQUESTED", "REVIEW_STARTED", "APPROVED", "REJECTED",
        "APPLIED", "CANCELLED",
    }


# ---------------------------------------------------------------------------
# Telemetry labels stay closed (§33)
# ---------------------------------------------------------------------------


def test_metric_vocabularies_are_closed_sets():
    assert governance_metrics.CAUSES == ("DISPUTE", "CORRECTION", "DIRECT")
    assert governance_metrics.RESOLUTIONS == (
        "UPHELD", "REJECTED", "INCONCLUSIVE", "INSUFFICIENT_EVIDENCE"
    )
    assert set(governance_metrics.CATEGORIES) == {
        "PROJECT_ASSOCIATION", "CLAIM_ASSOCIATION", "LOCATION_CONTEXT",
        "CONTEXTUAL_METADATA", "DESCRIPTIVE_FIELD", "EVIDENCE_FILE",
    }
    assert governance_metrics.REPROCESS_OUTCOMES == (
        "REPROCESSING_REQUESTED", "REPROCESSING_ALREADY_PENDING", "FAILED"
    )


def test_metric_recorders_never_raise_and_never_leak_identity_labels():
    # Out-of-vocabulary values fall back to a bounded label instead of
    # raising or minting new cardinality (§33: no user/evidence/dispute IDs).
    governance_metrics.record_dispute_created()
    governance_metrics.record_dispute_resolved("FRAUD")  # falls back
    governance_metrics.record_correction_requested("WEIRD")
    governance_metrics.record_correction_applied("WEIRD")
    governance_metrics.record_invalidation("VIBES")
    governance_metrics.record_reprocessing("MYSTERY")
    governance_metrics.record_reprocessing_failure()
    with governance_metrics.governance_operation_timer("create_dispute"):
        pass


def test_metrics_module_never_uses_identity_labels():
    import ast
    import inspect

    source = inspect.getsource(governance_metrics)
    tree = ast.parse(source)

    # The invariant is about label names, not about prose. The module docstring
    # documents the very rule this test enforces, so a raw substring scan reads
    # its own warning as a violation. Scan the executable AST instead: the names
    # below may appear as identifiers, attribute names, keyword names, or string
    # literals (a label is declared as a string), but never inside a docstring,
    # which is the only place prose about the rule belongs.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)

    def _is_docstring_constant(node):
        return isinstance(node, ast.Constant) and isinstance(node.value, str) \
            and node.value in docstrings

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            violations.append(node.id)
        elif isinstance(node, ast.Attribute):
            violations.append(node.attr)
        elif isinstance(node, ast.arg):
            violations.append(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            violations.append(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and not _is_docstring_constant(node):
            violations.append(node.value)

    for forbidden in ("user_id", "evidence_id", "dispute_id", "claim_id",
                      "project_id", "correction_id"):
        offenders = [v for v in violations if forbidden in v]
        assert not offenders, (
            f"{forbidden} used as a metric label/identifier: {offenders}"
        )
