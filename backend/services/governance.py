"""BE-021 governance service: dependency discovery, invalidation, reprocessing.

This module implements the milestone's core capability (§13): when a
governed correction/invalidation occurs, determine the derived intelligence
affected downstream and mark it STALE/INVALIDATED/SUPERSEDED — never delete
it. Traversal uses the BE-010 Evidence Graph as the primary relationship
source combined with the relational dependency chain, is deterministic and
bounded (visited set + depth cap + node cap; §16), and preserves provenance
and history everywhere.

Staleness policy (§14, §15, §8) — deterministic by cause:

- DISPUTE (challenge upheld)   -> jobs/fusion/explanations INVALIDATED
- CORRECTION + EVIDENCE_FILE   -> jobs/fusion/explanations SUPERSEDED
- CORRECTION (context) / DIRECT -> jobs/fusion/explanations STALE
- graph relationships           -> INVALIDATED (existing BE-010 vocabulary)
- integrity assessments         -> INVALIDATED (existing BE-011 vocabulary)

Review cases that reference invalidated intelligence are never auto-resolved
or reopened (§20): an append-only ``DEPENDENT_INTELLIGENCE_CHANGED`` case
event is recorded and the INTELLIGENCE_INVALIDATED audit event carries the
reach, leaving next actions to authorized reviewers.

Reprocessing (§17) is delegation only: a ReprocessingRequest row references
an AnalysisJob created through BE-005's existing ``create_analysis_job`` —
the worker, its lifecycle, and all historical runs remain untouched.

Conventions: ``ValueError`` for invalid input/semantic failures,
``LookupError`` for missing rows. Mutating operations commit.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    DISPUTE_TARGET_TYPES,
    INTELLIGENCE_STALENESS_STATES,
    INVALIDATION_CAUSES,
    AnalysisJob,
    Evidence,
    ExplanationRun,
    FusionRun,
    GraphRelationship,
    IntegrityAssessment,
    IntelligenceInvalidation,
    ReviewCase,
)
from backend.repositories import governance as governance_repo
from backend.services import audit_ledger as audit_service


logger = logging.getLogger(__name__)

TARGET_TYPES = frozenset(DISPUTE_TARGET_TYPES)
CAUSES = frozenset(INVALIDATION_CAUSES)
STALENESS_STATES = frozenset(INTELLIGENCE_STALENESS_STATES)

# Bounded traversal (§16, §38): deterministic caps; never unbounded recursion.
MAX_TRAVERSAL_DEPTH = 10
MAX_TRAVERSAL_NODES = 1000

RESULT_REQUESTED = "REPROCESSING_REQUESTED"
RESULT_ALREADY_PENDING = "REPROCESSING_ALREADY_PENDING"

# Kinds that carry a staleness/lifecycle column queryable for display.
_STATUS_COLUMNS = {
    "ANALYSIS_JOB": (AnalysisJob, "staleness"),
    "FUSION_RUN": (FusionRun, "staleness"),
    "EXPLANATION_RUN": (ExplanationRun, "staleness"),
    "INTEGRITY_ASSESSMENT": (IntegrityAssessment, "assessment_status"),
    "GRAPH_RELATIONSHIP": (GraphRelationship, "relationship_status"),
    "REVIEW_CASE": (ReviewCase, "status"),
    "EVIDENCE_CLAIM_RELATIONSHIP": (GraphRelationship, "relationship_status"),
    "FUSION_ASSESSMENT": (IntegrityAssessment, "assessment_status"),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_uuid(value: str | UUID, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error


def staleness_for_cause(cause: str, correction_category: str | None = None) -> str:
    """Deterministic staleness value for jobs/fusion/explanations (§14)."""
    if cause == "DISPUTE":
        return "INVALIDATED"
    if cause == "CORRECTION" and correction_category == "EVIDENCE_FILE":
        return "SUPERSEDED"
    return "STALE"


def _node_status(db: Session, kind: str, node_id: str) -> str | None:
    """Current staleness/lifecycle value of a discovered node, if it has one.

    ANALYSIS_RESULT nodes have no staleness column by design (§14): they
    inherit their parent job's staleness rather than duplicating a state
    machine, so they report None here.
    """
    entry = _STATUS_COLUMNS.get(kind)
    if entry is None:
        return None
    model, column = entry
    row = db.query(getattr(model, column)).filter(model.id == node_id).one_or_none()
    return str(row[0]) if row is not None else None


def _capped(ids: list[str], cap: int = 50) -> list[str]:
    """Audit payloads stay bounded: cap the id echo, keep exact counts."""
    return ids[:cap]


# ---------------------------------------------------------------------------
# Dependency discovery (bounded iterative BFS; §16)
# ---------------------------------------------------------------------------

def _children_of(db: Session, kind: str, row_id: str) -> list[tuple[str, str]]:
    """Deterministic one-hop downstream expansion of a dependency node.

    Returns ``(kind, id)`` pairs ordered by (created_at, id). Analysis
    results and vision detections have no staleness columns of their own:
    their parent job's staleness governs them (§14 — reuse existing
    lifecycles instead of inventing duplicate state machines), so they are
    discovered for lineage visibility but never marked.
    """
    children: list[tuple[str, str]] = []
    if kind == "EVIDENCE":
        for job_id in governance_repo.analysis_job_ids_for_evidence(db, row_id):
            children.append(("ANALYSIS_JOB", job_id))
        for run_id in governance_repo.fusion_run_ids_for_target(db, "EVIDENCE", row_id):
            children.append(("FUSION_RUN", run_id))
        for rel_id in governance_repo.relationship_ids_for_node_entity(db, "EVIDENCE", [row_id]):
            children.append(("GRAPH_RELATIONSHIP", rel_id))
        for case_id in governance_repo.review_case_ids_for_intelligence(db, evidence_id=row_id):
            children.append(("REVIEW_CASE", case_id))
    elif kind == "CLAIM":
        for run_id in governance_repo.fusion_run_ids_for_target(db, "CLAIM", row_id):
            children.append(("FUSION_RUN", run_id))
        for rel_id in governance_repo.relationship_ids_for_node_entity(db, "CLAIM", [row_id]):
            children.append(("GRAPH_RELATIONSHIP", rel_id))
        for case_id in governance_repo.review_case_ids_for_intelligence(db, claim_id=row_id):
            children.append(("REVIEW_CASE", case_id))
    elif kind == "ANALYSIS_JOB":
        for result_id in governance_repo.analysis_result_ids_for_jobs(db, [row_id]):
            children.append(("ANALYSIS_RESULT", result_id))
    elif kind == "ANALYSIS_RESULT":
        for rel_id in governance_repo.relationship_ids_for_node_entity(
            db, "ANALYSIS_RESULT", [row_id]
        ):
            children.append(("GRAPH_RELATIONSHIP", rel_id))
    elif kind == "FUSION_RUN":
        for run_id in governance_repo.explanation_run_ids_for_fusion_runs(db, [row_id]):
            children.append(("EXPLANATION_RUN", run_id))
        for assessment_id in governance_repo.assessment_ids_for_fusion_runs(db, [row_id]):
            children.append(("INTEGRITY_ASSESSMENT", assessment_id))
        for case_id in governance_repo.review_case_ids_for_intelligence(
            db, fusion_run_ids=[row_id]
        ):
            children.append(("REVIEW_CASE", case_id))
    return children


def discover_dependencies(
    db: Session,
    target_type: str,
    target_id: str,
    *,
    max_depth: int = MAX_TRAVERSAL_DEPTH,
    max_nodes: int = MAX_TRAVERSAL_NODES,
) -> dict:
    """Bounded, deterministic dependency traversal from a governed target.

    Returns a ``DependencyGraphResponse``-shaped dict: the target itself at
    depth 0, downstream nodes at increasing depth, ``truncated`` when the
    depth or node bound stopped the walk, and per-kind counts. The visited
    set prevents duplicate processing and cycle expansion (§16).
    """
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Unknown governance target type: {target_type!r}")
    target_id = _require_uuid(target_id, "target_id")
    if not 1 <= max_depth <= MAX_TRAVERSAL_DEPTH:
        raise ValueError(f"max_depth must be within [1, {MAX_TRAVERSAL_DEPTH}]")
    if not 1 <= max_nodes <= MAX_TRAVERSAL_NODES:
        raise ValueError(f"max_nodes must be within [1, {MAX_TRAVERSAL_NODES}]")

    target_row = governance_repo.get_target_row(db, target_type, target_id)
    if target_row is None:
        raise LookupError(f"{target_type} target not found: {target_id}")

    nodes: list[dict] = [
        {
            "kind": target_type,
            "id": target_id,
            "staleness": _node_status(db, target_type, target_id),
            "depth": 0,
        }
    ]
    counts: dict[str, int] = {target_type: 1}
    visited: set[tuple[str, str]] = {(target_type, target_id)}
    truncated = False
    frontier: list[tuple[str, str, int]] = [(target_type, target_id, 0)]

    while frontier:
        next_frontier: list[tuple[str, str, int]] = []
        for kind, row_id, depth in frontier:
            if depth >= max_depth:
                # Boundary node: report truncation only when it actually has
                # unfetched children (deterministic, bounded extra query).
                if _children_of(db, kind, row_id):
                    truncated = True
                continue
            for child_kind, child_id in _children_of(db, kind, row_id):
                if (child_kind, child_id) in visited:
                    continue  # duplicate dependency / cycle protection (§16)
                if len(nodes) >= max_nodes:
                    truncated = True
                    break
                visited.add((child_kind, child_id))
                nodes.append(
                    {
                        "kind": child_kind,
                        "id": child_id,
                        "staleness": _node_status(db, child_kind, child_id),
                        "depth": depth + 1,
                    }
                )
                counts[child_kind] = counts.get(child_kind, 0) + 1
                next_frontier.append((child_kind, child_id, depth + 1))
        frontier = next_frontier

    return {
        "target_type": target_type,
        "target_id": target_id,
        "max_depth": max_depth,
        "truncated": truncated,
        "nodes": nodes,
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Invalidation (§13, §15)
# ---------------------------------------------------------------------------

def _record_case_events(db: Session, case_ids: list[str], invalidation_id: str, reason: str) -> int:
    """Append DEPENDENT_INTELLIGENCE_CHANGED events to non-resolved review
    cases (§20). Cases are never mutated: their lifecycle stays with BE-013
    and their human decisions remain preserved."""
    from backend.repositories import review_case as case_repo

    recorded = 0
    for case_id in case_ids:
        case = db.query(ReviewCase).filter(ReviewCase.id == case_id).one_or_none()
        if case is None or case.status == "RESOLVED":
            continue
        case_repo.insert_event(
            db,
            case_id=case_id,
            event_type="DEPENDENT_INTELLIGENCE_CHANGED",
            from_status=case.status,
            to_status=case.status,
            actor_id=None,
            metadata={"invalidation_id": invalidation_id, "reason": reason},
        )
        recorded += 1
    return recorded


def invalidate_target(
    db: Session,
    *,
    target_type: str,
    target_id: str,
    cause: str,
    reason: str,
    invalidated_by: str,
    dispute_id: str | None = None,
    correction_id: str | None = None,
    correction_category: str | None = None,
    reprocess: bool = False,
) -> tuple[IntelligenceInvalidation, object | None]:
    """Invalidate a governed target's downstream derived intelligence.

    Marks (never deletes) every affected output within one transaction,
    records the reach on the invalidation row, emits the audit + notification
    twins, appends case events for referencing review cases (§20), and — for
    evidence targets with ``reprocess`` — delegates to the reprocessing flow
    (§17) as a follow-up transaction. Dispute/correction-caused invalidations
    are exactly-once per reference (§28); DIRECT repeats are legitimate
    distinct governance events (e.g. re-invalidating after reprocessing).

    Returns ``(invalidation, reprocessing_or_None)``.
    """
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Unknown governance target type: {target_type!r}")
    if cause not in CAUSES:
        raise ValueError(f"Unknown invalidation cause: {cause!r}")
    if not reason or not str(reason).strip():
        raise ValueError("Invalidation reason is required")
    if invalidated_by is None:
        raise ValueError("invalidated_by is required")
    target_id = _require_uuid(target_id, "target_id")
    invalidated_by = _require_uuid(invalidated_by, "invalidated_by")

    if dispute_id is not None:
        dispute_id = _require_uuid(dispute_id, "dispute_id")
    if correction_id is not None:
        correction_id = _require_uuid(correction_id, "correction_id")

    # §29: serialize concurrent invalidations of the same target. This lock is
    # also what makes the exactly-once checks below safe: two callers racing on
    # the same correction both arrive here, one waits, and the loser only
    # re-reads the existing invalidation AFTER the winner has committed. A
    # check placed before this lock would let both callers observe "absent" and
    # each insert a duplicate row (the ix_intelligence_invalidations_correction
    # index is intentionally non-unique, so the database does not catch it).
    target_row = governance_repo.lock_target_row(db, target_type, target_id)
    if target_row is None:
        raise LookupError(f"{target_type} target not found: {target_id}")

    if dispute_id is not None:
        existing = governance_repo.invalidation_for_dispute(db, dispute_id)
        if existing is not None:
            return existing, None  # exactly-once per dispute (§28)
    if correction_id is not None:
        existing = governance_repo.invalidation_for_correction(db, correction_id)
        if existing is not None:
            return existing, None  # exactly-once per correction (§28)

    project_id: str | None = None
    if target_type in {"EVIDENCE", "CLAIM", "REVIEW_CASE"}:
        project_id = str(target_row.project_id) if getattr(target_row, "project_id", None) else None

    staleness = staleness_for_cause(cause, correction_category)

    # ---- deterministic reach discovery (bounded, no payload retention) ----
    job_ids: list[str] = []
    fusion_ids: list[str] = []
    assessment_ids: list[str] = []
    relationship_ids: list[str] = []
    case_ids: list[str] = []

    if target_type == "EVIDENCE":
        job_ids = governance_repo.analysis_job_ids_for_evidence(db, target_id)
        fusion_ids = governance_repo.fusion_run_ids_for_target(db, "EVIDENCE", target_id)
        relationship_ids = governance_repo.relationship_ids_for_node_entity(
            db, "EVIDENCE", [target_id]
        )
        case_ids = governance_repo.review_case_ids_for_intelligence(db, evidence_id=target_id)
    elif target_type == "CLAIM":
        fusion_ids = governance_repo.fusion_run_ids_for_target(db, "CLAIM", target_id)
        relationship_ids = governance_repo.relationship_ids_for_node_entity(
            db, "CLAIM", [target_id]
        )
        case_ids = governance_repo.review_case_ids_for_intelligence(db, claim_id=target_id)
    elif target_type == "EVIDENCE_CLAIM_RELATIONSHIP":
        relationship_ids = [target_id]
    elif target_type == "FUSION_ASSESSMENT":
        assessment_ids = [target_id]
    elif target_type == "EXTERNAL_ASSERTION":
        pass  # immutable ingested record (§22): record-only invalidation
    elif target_type == "REVIEW_CASE":
        case_ids = [target_id]

    explanation_ids = governance_repo.explanation_run_ids_for_fusion_runs(db, fusion_ids)
    assessment_ids = list(
        dict.fromkeys(
            assessment_ids + governance_repo.assessment_ids_for_fusion_runs(db, fusion_ids)
        )
    )

    # Only currently-ACTIVE relationships are affected by THIS invalidation:
    # previously invalidated/superseded edges keep their earlier history and
    # are neither re-counted nor re-audited.
    active_rel_ids: list[str] = []
    if relationship_ids:
        rows = (
            db.query(GraphRelationship.id)
            .filter(
                GraphRelationship.id.in_(relationship_ids),
                GraphRelationship.relationship_status == "ACTIVE",
            )
            .order_by(GraphRelationship.created_at.asc(), GraphRelationship.id.asc())
            .all()
        )
        active_rel_ids = [str(row[0]) for row in rows]

    # ---- marking (bulk UPDATEs bounded by enumerated ids; never deletes) ----
    marked_jobs = governance_repo.mark_analysis_jobs(db, job_ids, staleness)
    marked_fusion = governance_repo.mark_fusion_runs(db, fusion_ids, staleness)
    marked_explanations = governance_repo.mark_explanation_runs(db, explanation_ids, staleness)
    marked_assessments = governance_repo.mark_integrity_assessments(
        db, assessment_ids, "INVALIDATED"
    )
    marked_relationships = governance_repo.mark_graph_relationships(
        db, active_rel_ids, "INVALIDATED"
    )

    # Per-relationship audit twins keep BE-010's lifecycle audit consistent.
    for rel_id in active_rel_ids:
        rel = (
            db.query(GraphRelationship)
            .filter(GraphRelationship.id == rel_id)
            .one_or_none()
        )
        if rel is None:
            continue
        audit_service.append_event(
            db,
            event_type="GRAPH_RELATIONSHIP_INVALIDATED",
            action="transition",
            resource_type="graph_relationships",
            resource_id=rel_id,
            actor_id=invalidated_by,
            project_id=project_id,
            payload={
                "graph_relationship_id": rel_id,
                "relationship_type": rel.relationship_type,
                "from_status": "ACTIVE",
                "to_status": "INVALIDATED",
                "invalidation_cause": cause,
            },
            source="governance_service",
        )

    # ---- record the invalidation with its bounded reach ----
    invalidation = governance_repo.insert_invalidation(
        db,
        target_type=target_type,
        target_id=target_id,
        project_id=project_id,
        cause=cause,
        dispute_id=dispute_id,
        correction_id=correction_id,
        reason=str(reason),
        invalidated_by=invalidated_by,
        affected_analysis=marked_jobs,
        affected_fusion=marked_fusion,
        affected_explanations=marked_explanations,
        affected_relationships=marked_relationships,
        affected_assessments=marked_assessments,
    )

    recorded_cases = _record_case_events(db, case_ids, str(invalidation.id), str(reason))

    audit_service.append_event(
        db,
        event_type="INTELLIGENCE_INVALIDATED",
        action="invalidate",
        resource_type="intelligence_invalidations",
        resource_id=invalidation.id,
        actor_id=invalidated_by,
        project_id=project_id,
        payload={
            "invalidation_id": str(invalidation.id),
            "target_type": target_type,
            "target_id": target_id,
            "cause": cause,
            "dispute_id": dispute_id,
            "correction_id": correction_id,
            "staleness_applied": staleness,
            "affected_analysis": marked_jobs,
            "affected_fusion": marked_fusion,
            "affected_explanations": marked_explanations,
            "affected_relationships": marked_relationships,
            "affected_assessments": marked_assessments,
            "review_cases_notified": recorded_cases,
            "affected_analysis_job_ids": _capped(job_ids),
            "affected_fusion_run_ids": _capped(fusion_ids),
            "affected_relationship_ids": _capped(active_rel_ids),
        },
        source="governance_service",
    )

    try:
        from backend.services import notification as notif_service

        notif_service.emit_notification_event(
            db,
            event_type="INTELLIGENCE_INVALIDATED",
            aggregate_type="INTELLIGENCE_INVALIDATION",
            aggregate_id=str(invalidation.id),
            payload={
                "invalidation_id": str(invalidation.id),
                "project_id": project_id,
                "target_type": target_type,
                "target_id": target_id,
                "cause": cause,
                "resource_type": "intelligence_invalidation",
                "resource_id": str(invalidation.id),
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to emit notification for invalidation %s: %s", invalidation.id, exc
        )

    db.commit()
    db.refresh(invalidation)
    from backend.observability import governance_metrics

    governance_metrics.record_invalidation(cause)
    logger.info(
        "intelligence invalidated id=%s target=%s:%s cause=%s reach=(jobs=%d fusion=%d "
        "explanations=%d relationships=%d assessments=%d cases=%d)",
        invalidation.id, target_type, target_id, cause,
        marked_jobs, marked_fusion, marked_explanations,
        marked_relationships, marked_assessments, recorded_cases,
    )

    # ---- follow-up: reprocessing delegation (§17) ----
    reprocessing = None
    if reprocess and target_type == "EVIDENCE":
        try:
            _, reprocessing = request_reprocessing(
                db,
                evidence_id=target_id,
                requested_by=invalidated_by,
                reason=f"Reprocessing after {cause} invalidation: {reason}",
                invalidation_id=str(invalidation.id),
            )
        except (RuntimeError, LookupError) as exc:
            # The invalidation itself is committed and authoritative; a
            # failed reprocessing is recorded on its request row + audit
            # event and can be retried via the explicit reprocess endpoint.
            logger.warning(
                "Reprocessing after invalidation %s failed: %s", invalidation.id, exc
            )
            reprocessing = None
    return invalidation, reprocessing


# ---------------------------------------------------------------------------
# Reprocessing (delegation only, §17)
# ---------------------------------------------------------------------------

def request_reprocessing(
    db: Session,
    *,
    evidence_id: str,
    requested_by: str,
    reason: str,
    invalidation_id: str | None = None,
    queue=None,
) -> tuple[object, str]:
    """Request reprocessing of one evidence item through the EXISTING
    pipeline (§17). One PENDING request per evidence item (§28); duplicates
    return the existing request. Delegation creates the AnalysisJob via
    BE-005's ``create_analysis_job`` — no worker logic is duplicated.

    Returns ``(reprocessing_request, result)`` where result is
    ``REPROCESSING_REQUESTED`` or ``REPROCESSING_ALREADY_PENDING``.
    """
    evidence_id = _require_uuid(evidence_id, "evidence_id")
    if requested_by is None:
        raise ValueError("requested_by is required")
    requested_by = _require_uuid(requested_by, "requested_by")
    if invalidation_id is not None:
        invalidation_id = _require_uuid(invalidation_id, "invalidation_id")
    if not reason or not str(reason).strip():
        raise ValueError("Reprocessing reason is required")

    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
    if evidence is None:
        raise LookupError(f"Evidence not found: {evidence_id}")

    pending = governance_repo.pending_reprocessing_for_evidence(db, evidence_id)
    if pending is not None:
        from backend.observability import governance_metrics

        governance_metrics.record_reprocessing(RESULT_ALREADY_PENDING)
        return pending, RESULT_ALREADY_PENDING

    project_id = str(evidence.project_id) if evidence.project_id else None
    try:
        request = governance_repo.insert_reprocessing(
            db,
            evidence_id=evidence_id,
            project_id=project_id,
            invalidation_id=invalidation_id,
            requested_by=requested_by,
            reason=str(reason),
        )
        audit_service.append_event(
            db,
            event_type="INTELLIGENCE_REPROCESS_REQUESTED",
            action="create",
            resource_type="reprocessing_requests",
            resource_id=request.id,
            actor_id=requested_by,
            project_id=project_id,
            payload={
                "reprocessing_request_id": str(request.id),
                "evidence_id": evidence_id,
                "invalidation_id": invalidation_id,
            },
            source="governance_service",
        )
        # Persist PENDING first: the partial-unique index guards the
        # concurrent-duplicate race (§29) before any side effects.
        db.commit()
    except IntegrityError:
        db.rollback()
        pending = governance_repo.pending_reprocessing_for_evidence(db, evidence_id)
        if pending is not None:
            return pending, RESULT_ALREADY_PENDING
        raise

    # ---- delegate to BE-005 (its function commits + enqueues itself) ----
    from backend.services.analysis_jobs import create_analysis_job

    try:
        job = create_analysis_job(evidence_id=evidence_id, db=db, queue=queue)
    except (RuntimeError, LookupError) as exc:
        request.status = "FAILED"
        from backend.observability import governance_metrics

        governance_metrics.record_reprocessing("FAILED")
        governance_metrics.record_reprocessing_failure()
        audit_service.append_event(
            db,
            event_type="INTELLIGENCE_REPROCESS_FAILED",
            action="fail",
            resource_type="reprocessing_requests",
            resource_id=request.id,
            actor_id=requested_by,
            project_id=project_id,
            payload={
                "reprocessing_request_id": str(request.id),
                "evidence_id": evidence_id,
                "error": str(exc),
            },
            source="governance_service",
        )
        db.commit()
        raise

    request.analysis_job_id = job.id
    db.commit()
    db.refresh(request)
    from backend.observability import governance_metrics

    governance_metrics.record_reprocessing(RESULT_REQUESTED)
    logger.info(
        "reprocessing requested id=%s evidence=%s job=%s",
        request.id, evidence_id, job.id,
    )
    return request, RESULT_REQUESTED


def complete_reprocessing(
    db: Session,
    *,
    reprocessing_id: str | None = None,
    analysis_job_id: str | None = None,
    completed_by: str | None = None,
) -> object:
    """Mark a PENDING reprocessing request COMPLETED (idempotent) and emit
    its audit + notification twins. Called by the analysis worker hook once
    the delegated BE-005 job finishes (§17)."""
    reprocessing_id = (
        _require_uuid(reprocessing_id, "reprocessing_id") if reprocessing_id else None
    )
    analysis_job_id = (
        _require_uuid(analysis_job_id, "analysis_job_id") if analysis_job_id else None
    )
    if reprocessing_id is None and analysis_job_id is None:
        raise ValueError("reprocessing_id or analysis_job_id is required")

    if reprocessing_id is not None:
        request = governance_repo.lock_reprocessing(db, reprocessing_id)
    else:
        request = governance_repo.lock_pending_reprocessing_for_job(db, analysis_job_id)
    if request is None:
        raise LookupError("Reprocessing request not found")

    if request.status == "COMPLETED":
        return request
    if request.status != "PENDING":
        raise ValueError(
            f"Only PENDING reprocessing requests can complete (current: {request.status})"
        )

    request.status = "COMPLETED"
    request.completed_at = utc_now()
    audit_service.append_event(
        db,
        event_type="INTELLIGENCE_REPROCESS_COMPLETED",
        action="complete",
        resource_type="reprocessing_requests",
        resource_id=request.id,
        actor_id=completed_by,
        project_id=str(request.project_id) if request.project_id else None,
        payload={
            "reprocessing_request_id": str(request.id),
            "evidence_id": str(request.evidence_id),
            "analysis_job_id": str(request.analysis_job_id)
            if request.analysis_job_id
            else None,
        },
        source="governance_service",
    )
    try:
        from backend.services import notification as notif_service

        notif_service.emit_notification_event(
            db,
            event_type="REPROCESSING_COMPLETED",
            aggregate_type="REPROCESSING_REQUEST",
            aggregate_id=str(request.id),
            payload={
                "reprocessing_request_id": str(request.id),
                "project_id": str(request.project_id) if request.project_id else None,
                "evidence_id": str(request.evidence_id),
                "analysis_job_id": str(request.analysis_job_id)
                if request.analysis_job_id
                else None,
                "resource_type": "reprocessing_request",
                "resource_id": str(request.id),
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to emit notification for reprocessing %s: %s", request.id, exc
        )
    db.commit()
    db.refresh(request)
    return request


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_invalidation(db: Session, invalidation_id: str) -> IntelligenceInvalidation:
    invalidation = governance_repo.get_invalidation(
        db, _require_uuid(invalidation_id, "invalidation_id")
    )
    if invalidation is None:
        raise LookupError(f"Invalidation not found: {invalidation_id}")
    return invalidation


def get_reprocessing(db: Session, reprocessing_id: str):
    request = governance_repo.get_reprocessing(
        db, _require_uuid(reprocessing_id, "reprocessing_id")
    )
    if request is None:
        raise LookupError(f"Reprocessing request not found: {reprocessing_id}")
    return request
