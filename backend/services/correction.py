"""BE-021 correction service: governed changes to mutable evidence context.

Corrections change *context* only. The original evidence bytes, storage key,
and cryptographic identity are immutable (§8): no category ever rewrites
them, and EVIDENCE_FILE corrections create a NEW evidence version linked to
the original via a BE-010 ``DERIVED_FROM`` lineage edge (NEW -> OLD, §9) that
itself passes through the normal ingestion pipeline.

Approval and application are distinct lifecycle steps (§10). Role
separation (§12): the requester can never approve or apply their own
correction. Application triggers intelligence invalidation of the corrected
evidence's downstream (§13) exactly once per correction (§28).

Conventions: ``ValueError`` for invalid input/semantic failures,
``LookupError`` for missing rows. Mutating operations commit.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    CORRECTION_CATEGORIES,
    CORRECTION_STATUSES,
    CorrectionRequest,
    Evidence,
    EvidenceMetadata,
)
from backend.repositories import correction as correction_repo
from backend.services import audit_ledger as audit_service


logger = logging.getLogger(__name__)

CATEGORIES = frozenset(CORRECTION_CATEGORIES)
STATUSES = frozenset(CORRECTION_STATUSES)

# Explicit lifecycle matrix (§10): approval and application are distinct;
# APPLIED / REJECTED / CANCELLED are terminal.
TRANSITIONS: dict[str, frozenset[str]] = {
    "REQUESTED": frozenset({"UNDER_REVIEW", "APPROVED", "REJECTED", "CANCELLED"}),
    "UNDER_REVIEW": frozenset({"APPROVED", "REJECTED", "CANCELLED"}),
    "APPROVED": frozenset({"APPLIED", "CANCELLED"}),
    "APPLIED": frozenset(),
    "REJECTED": frozenset(),
    "CANCELLED": frozenset(),
}

# Which categories replace an association outright (vs merge/update).
_ASSOCIATION_CATEGORIES = frozenset({"PROJECT_ASSOCIATION", "CLAIM_ASSOCIATION"})

# Domain event -> audit event mapping (BE-015).
CORRECTION_AUDIT_TYPES = {
    "REQUESTED": "CORRECTION_REQUESTED",
    "REVIEW_STARTED": "CORRECTION_REVIEW_STARTED",
    "APPROVED": "CORRECTION_APPROVED",
    "REJECTED": "CORRECTION_REJECTED",
    "APPLIED": "CORRECTION_APPLIED",
    "CANCELLED": "CORRECTION_CANCELLED",
}

# Domain event -> notification type mapping (BE-018 §24). IDs only.
CORRECTION_NOTIFICATION_TYPES = {
    "APPROVED": "CORRECTION_APPROVED",
    "REJECTED": "CORRECTION_REJECTED",
    "APPLIED": "CORRECTION_APPLIED",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_uuid(value: str | UUID, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error


def _optional_uuid(value: str | UUID | None, label: str) -> str | None:
    if value is None:
        return None
    return _require_uuid(value, label)


def validate_transition(from_status: str, to_status: str) -> None:
    """Explicitly validate a lifecycle transition (§10; never silent)."""
    if from_status not in TRANSITIONS:
        raise ValueError(f"Unknown correction status: {from_status!r}")
    if to_status not in STATUSES:
        raise ValueError(f"Unknown correction status: {to_status!r}")
    if to_status not in TRANSITIONS[from_status]:
        raise ValueError(f"Invalid transition: {from_status} -> {to_status}")


# ---------------------------------------------------------------------------
# Requested-change validation (per category; validated at request time and
# re-validated at application time so approval decisions match reality)
# ---------------------------------------------------------------------------

def validate_requested_change(
    db: Session, evidence_id: str, category: str, change: dict
) -> dict:
    """Validate the structure and referents of a requested change.

    Returns the normalized change to persist. Raises ``ValueError`` for
    malformed changes and ``LookupError`` for missing referenced rows.
    """
    if not isinstance(change, dict) or not change:
        raise ValueError("requested_change must be a non-empty object")
    if category not in CATEGORIES:
        raise ValueError(f"Unknown correction category: {category!r}")

    if category == "PROJECT_ASSOCIATION":
        if set(change) != {"project_id"}:
            raise ValueError("PROJECT_ASSOCIATION change requires exactly 'project_id'")
        if change["project_id"] is not None:
            from backend.db.models import Project

            project_id = _require_uuid(change["project_id"], "project_id")
            if db.query(Project.id).filter(Project.id == project_id).one_or_none() is None:
                raise LookupError(f"Project not found: {project_id}")
            return {"project_id": project_id}
        return {"project_id": None}

    if category == "CLAIM_ASSOCIATION":
        if set(change) != {"claim_id"}:
            raise ValueError("CLAIM_ASSOCIATION change requires exactly 'claim_id'")
        if change["claim_id"] is not None:
            from backend.db.models import Claim

            claim_id = _require_uuid(change["claim_id"], "claim_id")
            if db.query(Claim.id).filter(Claim.id == claim_id).one_or_none() is None:
                raise LookupError(f"Claim not found: {claim_id}")
            return {"claim_id": claim_id}
        return {"claim_id": None}

    if category == "LOCATION_CONTEXT":
        if not {"latitude", "longitude"} <= set(change):
            raise ValueError("LOCATION_CONTEXT change requires 'latitude' and 'longitude'")
        try:
            latitude = float(change["latitude"])
            longitude = float(change["longitude"])
        except (TypeError, ValueError) as error:
            raise ValueError("latitude/longitude must be numeric") from error
        if not -90.0 <= latitude <= 90.0:
            raise ValueError("latitude must be within [-90, 90]")
        if not -180.0 <= longitude <= 180.0:
            raise ValueError("longitude must be within [-180, 180]")
        return {"latitude": latitude, "longitude": longitude}

    if category == "CONTEXTUAL_METADATA":
        metadata = change.get("metadata")
        if not isinstance(metadata, dict) or not metadata:
            raise ValueError("CONTEXTUAL_METADATA change requires a non-empty 'metadata' object")
        return {"metadata": metadata}

    if category == "DESCRIPTIVE_FIELD":
        if set(change) != {"filename"}:
            raise ValueError("DESCRIPTIVE_FIELD change requires exactly 'filename'")
        filename = change["filename"]
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("filename must be a non-empty string")
        if len(filename) > 512:
            raise ValueError("filename must be at most 512 characters")
        return {"filename": filename.strip()}

    # EVIDENCE_FILE
    if set(change) != {"new_evidence_id"}:
        raise ValueError("EVIDENCE_FILE change requires exactly 'new_evidence_id'")
    new_evidence_id = _require_uuid(change["new_evidence_id"], "new_evidence_id")
    if new_evidence_id == str(evidence_id):
        raise ValueError("new_evidence_id must differ from the corrected evidence")
    replacement = db.query(Evidence).filter(Evidence.id == new_evidence_id).one_or_none()
    if replacement is None:
        raise LookupError(f"Replacement evidence not found: {new_evidence_id}")
    return {"new_evidence_id": new_evidence_id}


# ---------------------------------------------------------------------------
# Audit / notification twins
# ---------------------------------------------------------------------------

def _audit_correction_event(
    db: Session,
    correction,
    event_type: str,
    actor_id: str | None,
    action: str,
    extra_payload: dict | None = None,
) -> None:
    audit_type = CORRECTION_AUDIT_TYPES.get(event_type)
    if audit_type is None:
        return
    audit_service.append_event(
        db,
        event_type=audit_type,
        action=action,
        resource_type="correction_requests",
        resource_id=correction.id,
        actor_id=actor_id,
        project_id=str(correction.project_id) if correction.project_id else None,
        payload={
            "correction_id": correction.id,
            "target_type": correction.target_type,
            "target_id": str(correction.target_id),
            "category": correction.category,
            "status": correction.status,
            **(extra_payload or {}),
        },
        source="correction_service",
    )


def _emit_correction_notification(
    db: Session, correction, event_type: str, metadata: dict | None
) -> None:
    try:
        from backend.services import notification as notif_service

        notif_type = CORRECTION_NOTIFICATION_TYPES.get(event_type)
        if notif_type is None:
            return
        payload: dict = {
            "correction_id": str(correction.id),
            "project_id": str(correction.project_id) if correction.project_id else None,
            "category": correction.category,
            "status": correction.status,
            "resource_type": "correction_request",
            "resource_id": str(correction.id),
        }
        if event_type == "APPLIED" and metadata:
            payload["applied"] = bool(metadata.get("applied"))
        notif_service.emit_notification_event(
            db,
            event_type=notif_type,
            aggregate_type="CORRECTION_REQUEST",
            aggregate_id=str(correction.id),
            payload=payload,
        )
    except Exception as exc:
        logger.warning(
            "Failed to emit notification for correction %s event %s: %s",
            correction.id, event_type, exc,
        )


# ---------------------------------------------------------------------------
# Workflow helper (review_case _apply pattern)
# ---------------------------------------------------------------------------

def _apply_status(
    db: Session,
    correction,
    to_status: str,
    event_type: str,
    actor_id: str | None,
    event_metadata: dict | None = None,
    **fields,
):
    validate_transition(correction.status, to_status)
    from_status = correction.status
    for name, value in fields.items():
        setattr(correction, name, value)
    correction.status = to_status
    correction_repo.insert_event(
        db,
        correction_id=correction.id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        metadata=event_metadata or {},
    )
    _audit_correction_event(
        db,
        correction,
        event_type,
        actor_id,
        action="transition"
        if to_status not in {"APPROVED", "REJECTED", "APPLIED", "CANCELLED"}
        else to_status.lower(),
        extra_payload={"from_status": from_status, "to_status": to_status},
    )
    _emit_correction_notification(db, correction, event_type, event_metadata)
    db.commit()
    db.refresh(correction)
    return correction


def _get_or_raise(db: Session, correction_id: str):
    correction = correction_repo.get_correction(db, _require_uuid(correction_id, "correction_id"))
    if correction is None:
        raise LookupError(f"Correction request not found: {correction_id}")
    return correction


def _lock_or_raise(db: Session, correction_id: str):
    correction = correction_repo.lock_correction(db, _require_uuid(correction_id, "correction_id"))
    if correction is None:
        raise LookupError(f"Correction request not found: {correction_id}")
    return correction


def _enforce_role_separation(correction, actor_id: str | None, action: str) -> None:
    """Requester may never approve or apply their own correction (§12)."""
    if actor_id is not None and str(actor_id) == str(correction.requester_id):
        raise ValueError(
            f"Role separation violation: the correction requester cannot {action} it"
        )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def create_correction(
    db: Session,
    *,
    target_id: str,
    category: str,
    requested_change: dict,
    reason: str,
    requester_id: str,
    target_type: str = "EVIDENCE",
) -> tuple[object, bool]:
    """Create a correction request against mutable evidence context (§10).

    Idempotency: an identical active request (same target, category, and
    requested change) is returned instead of a duplicate (§28).
    """
    if target_type != "EVIDENCE":
        raise ValueError(f"Correction target type not supported: {target_type!r}")
    target_id = _require_uuid(target_id, "target_id")
    requester_id = _require_uuid(requester_id, "requester_id")
    if not reason or not str(reason).strip():
        raise ValueError("Correction reason is required")
    if category not in CATEGORIES:
        raise ValueError(f"Unknown correction category: {category!r}")

    evidence = db.query(Evidence).filter(Evidence.id == target_id).one_or_none()
    if evidence is None:
        raise LookupError(f"Evidence not found: {target_id}")

    normalized = validate_requested_change(db, target_id, category, requested_change)

    # Idempotency window (§28): an identical change, still active, on the same
    # target + category returns the existing request instead of a duplicate.
    existing = (
        db.query(CorrectionRequest)
        .filter(
            CorrectionRequest.target_id == target_id,
            CorrectionRequest.category == category,
            CorrectionRequest.status.in_(("REQUESTED", "UNDER_REVIEW", "APPROVED")),
        )
        .order_by(CorrectionRequest.created_at.desc(), CorrectionRequest.id.desc())
        .all()
    )
    for row in existing:
        if row.requested_change == normalized:
            return row, False

    try:
        correction = correction_repo.insert_correction(
            db,
            target_type=target_type,
            target_id=target_id,
            project_id=str(evidence.project_id) if evidence.project_id else None,
            category=category,
            requested_change=normalized,
            reason=str(reason),
            requester_id=requester_id,
        )
        correction_repo.insert_event(
            db,
            correction_id=correction.id,
            event_type="REQUESTED",
            from_status=None,
            to_status="REQUESTED",
            actor_id=requester_id,
            metadata={"category": category},
        )
        _audit_correction_event(
            db, correction, "REQUESTED", requester_id, "create",
            {"requester_id": requester_id},
        )
        db.commit()
        from backend.observability import governance_metrics

        governance_metrics.record_correction_requested(category)
    except IntegrityError:
        # Concurrent duplicate: the partial-unique index
        # uq_correction_active_target_category_requester picked a winner.
        # Identical change -> idempotent return; a different active change by
        # the same requester on the same target+category is refused.
        db.rollback()
        winner = (
            db.query(CorrectionRequest)
            .filter(
                CorrectionRequest.target_id == target_id,
                CorrectionRequest.category == category,
                CorrectionRequest.requester_id == requester_id,
                CorrectionRequest.status.in_(("REQUESTED", "UNDER_REVIEW", "APPROVED")),
            )
            .order_by(CorrectionRequest.created_at.desc(), CorrectionRequest.id.desc())
            .first()
        )
        if winner is not None and winner.requested_change == normalized:
            return winner, False
        raise ValueError(
            "An active correction request already exists for this target and "
            "category by this requester"
        )
    db.refresh(correction)
    logger.info(
        "correction request created id=%s category=%s target=EVIDENCE:%s",
        correction.id, category, target_id,
    )
    return correction, True


# ---------------------------------------------------------------------------
# Workflow actions
# ---------------------------------------------------------------------------

def start_review(
    db: Session, correction_id: str, *, actor_id: str | None = None
):
    """REQUESTED -> UNDER_REVIEW. Idempotent when already under review."""
    correction = _lock_or_raise(db, correction_id)
    _enforce_role_separation(correction, actor_id, "review")
    if correction.status == "UNDER_REVIEW":
        return correction
    return _apply_status(
        db, correction, "UNDER_REVIEW", "REVIEW_STARTED", actor_id,
    )


def approve_correction(
    db: Session, correction_id: str, *, rationale: str, resolver_id: str | None = None
):
    """REQUESTED/UNDER_REVIEW -> APPROVED. Idempotent when already approved
    by the same resolver (§28); a *different* resolver's approval attempt on
    an approved request is a no-op returning the existing record."""
    correction = _lock_or_raise(db, correction_id)
    _enforce_role_separation(correction, resolver_id, "approve")
    if not rationale or not str(rationale).strip():
        raise ValueError("Approval rationale is required")
    if correction.status == "APPROVED":
        return correction
    return _apply_status(
        db, correction, "APPROVED", "APPROVED", resolver_id,
        {"rationale": str(rationale)},
        resolver_id=resolver_id,
        resolution_rationale=str(rationale),
        resolved_at=utc_now(),
    )


def reject_correction(
    db: Session, correction_id: str, *, rationale: str, resolver_id: str | None = None
):
    """REQUESTED/UNDER_REVIEW -> REJECTED. Idempotent when already rejected."""
    correction = _lock_or_raise(db, correction_id)
    _enforce_role_separation(correction, resolver_id, "reject")
    if not rationale or not str(rationale).strip():
        raise ValueError("Rejection rationale is required")
    if correction.status == "REJECTED":
        return correction
    return _apply_status(
        db, correction, "REJECTED", "REJECTED", resolver_id,
        {"rationale": str(rationale)},
        resolver_id=resolver_id,
        resolution_rationale=str(rationale),
        resolved_at=utc_now(),
    )


def cancel_correction(
    db: Session, correction_id: str, *, reason: str, actor_id: str | None = None
):
    """REQUESTED/UNDER_REVIEW/APPROVED -> CANCELLED by the requester."""
    correction = _lock_or_raise(db, correction_id)
    if actor_id is not None and str(actor_id) != str(correction.requester_id):
        raise ValueError("Only the correction requester may cancel it")
    if not reason or not str(reason).strip():
        raise ValueError("Cancellation reason is required")
    if correction.status == "CANCELLED":
        return correction
    return _apply_status(
        db, correction, "CANCELLED", "CANCELLED", actor_id, {"reason": str(reason)}
    )


# ---------------------------------------------------------------------------
# Application (per-category; evidence bytes stay immutable, §8)
# ---------------------------------------------------------------------------

def _apply_change(db: Session, evidence: Evidence, category: str, change: dict) -> dict:
    """Apply one approved change to the evidence's mutable context.

    Returns the ``applied_change`` record (previous + applied values).
    Never touches filename bytes, storage_key, sha256, or file_size — except
    DESCRIPTIVE_FIELD which renames the *label* only.
    """
    from sqlalchemy import func

    applied: dict = {"category": category, "previous": {}, "applied": {}}

    if category == "PROJECT_ASSOCIATION":
        applied["previous"]["project_id"] = (
            str(evidence.project_id) if evidence.project_id else None
        )
        evidence.project_id = change["project_id"]
        applied["applied"]["project_id"] = change["project_id"]

    elif category == "CLAIM_ASSOCIATION":
        applied["previous"]["claim_id"] = (
            str(evidence.claim_id) if evidence.claim_id else None
        )
        evidence.claim_id = change["claim_id"]
        applied["applied"]["claim_id"] = change["claim_id"]

    elif category == "LOCATION_CONTEXT":
        applied["previous"]["location"] = None  # geometry not echoed into JSON
        evidence.location = func.ST_SetSRID(
            func.ST_MakePoint(change["longitude"], change["latitude"]), 4326
        )
        applied["applied"]["location"] = {
            "latitude": change["latitude"],
            "longitude": change["longitude"],
        }

    elif category == "CONTEXTUAL_METADATA":
        row = (
            db.query(EvidenceMetadata)
            .filter(EvidenceMetadata.evidence_id == str(evidence.id))
            .one_or_none()
        )
        old_metadata = dict(row.metadata_json) if row is not None and row.metadata_json else {}
        new_metadata = {**old_metadata, **change["metadata"]}
        if row is None:
            row = EvidenceMetadata(evidence_id=str(evidence.id), metadata_json=new_metadata)
            db.add(row)
        else:
            row.metadata_json = new_metadata
        touched_previous = {
            key: old_metadata.get(key) for key in change["metadata"]
        }
        applied["previous"]["metadata"] = touched_previous
        applied["applied"]["metadata"] = change["metadata"]

    elif category == "DESCRIPTIVE_FIELD":
        applied["previous"]["filename"] = evidence.filename
        evidence.filename = change["filename"]
        applied["applied"]["filename"] = change["filename"]

    elif category == "EVIDENCE_FILE":
        # Version lineage (§8, §9) is created AFTER the correction commits
        # (see apply_correction): the original row and bytes are untouched
        # here, and the replacement evidence has already passed the normal
        # ingestion pipeline. Only the applied record is prepared.
        applied["applied"]["new_evidence_id"] = change["new_evidence_id"]

    return applied


def _ensure_evidence_lineage(db: Session, correction) -> None:
    """Create (idempotently) the NEW -> OLD ``DERIVED_FROM`` lineage edge for
    an EVIDENCE_FILE correction (§8, §9). The BE-010 service owns the graph:
    no second lineage system, and the dedupe key makes retries safe."""
    if correction.category != "EVIDENCE_FILE":
        return
    from backend.services import evidence_graph as graph_service

    change = correction.requested_change or {}
    new_evidence_id = change.get("new_evidence_id")
    if not new_evidence_id:
        raise ValueError("EVIDENCE_FILE correction is missing new_evidence_id")
    graph_service.create_relationship(
        db,
        source_type="EVIDENCE",
        source_id=str(new_evidence_id),
        target_type="EVIDENCE",
        target_id=str(correction.target_id),
        relationship_type="DERIVED_FROM",
        provenance={
            "source": "correction_service",
            "method": "evidence_version_supersession",
            "method_version": "be021",
            "correction_id": str(correction.id),
        },
        explanation="New evidence version derived from the corrected original.",
    )


def _invalidate_for_correction(
    db: Session, correction, invalidated_by: str | None
) -> tuple[object | None, object | None]:
    """Invalidate downstream intelligence for an applied correction, exactly
    once per correction (§13, §28). EVIDENCE_FILE corrections never request
    reprocessing of the superseded original: the replacement evidence has
    already passed the normal ingestion pipeline (§8)."""
    from backend.repositories import governance as governance_repo
    from backend.services import governance as governance_service

    invalidation = governance_repo.invalidation_for_correction(db, str(correction.id))
    reprocessing = None
    if invalidation is None:
        invalidation, reprocessing = governance_service.invalidate_target(
            db,
            target_type=correction.target_type,
            target_id=str(correction.target_id),
            cause="CORRECTION",
            reason=f"Correction {correction.id} applied: {correction.category}",
            invalidated_by=invalidated_by,
            dispute_id=None,
            correction_id=str(correction.id),
            correction_category=correction.category,
            reprocess=correction.category != "EVIDENCE_FILE",
        )
    return invalidation, reprocessing


def apply_correction(
    db: Session,
    correction_id: str,
    *,
    applied_by: str | None = None,
) -> tuple[object, object | None, object | None]:
    """APPROVED -> APPLIED: mutate context, record, then invalidate
    downstream intelligence exactly once per correction (§13, §28).

    Sequencing: the correction state commits first (the authoritative
    governance record), then the version-lineage edge and the downstream
    invalidation run as follow-up transactions. Retrying an applied
    correction is idempotent and heals any step a crash interrupted:
    lineage and invalidation are re-ensured, never duplicated.

    Returns ``(correction, invalidation, reprocessing_or_None)``.
    """
    correction = _lock_or_raise(db, correction_id)
    _enforce_role_separation(correction, applied_by, "apply")

    if correction.status == "APPLIED":
        # Idempotent retry (§28) + crash healing: re-ensure the follow-up
        # steps without duplicating any record. Same ordering as the fresh-apply
        # path below — invalidation first, lineage second — so a crash between
        # the two steps cannot heal itself into an INVALIDATED lineage edge.
        invalidation, reprocessing = _invalidate_for_correction(db, correction, applied_by)
        _ensure_evidence_lineage(db, correction)
        return correction, invalidation, reprocessing

    if correction.status != "APPROVED":
        raise ValueError(
            f"Only APPROVED corrections can be applied (current: {correction.status})"
        )

    evidence = (
        db.query(Evidence)
        .filter(Evidence.id == str(correction.target_id))
        .one_or_none()
    )
    if evidence is None:
        raise LookupError(f"Corrected evidence not found: {correction.target_id}")

    # Re-validate: the world may have changed since approval.
    change = validate_requested_change(
        db, str(correction.target_id), correction.category, correction.requested_change
    )

    applied_change = _apply_change(db, evidence, correction.category, change)
    correction.applied_change = applied_change
    correction.applied_by = applied_by
    correction.applied_at = utc_now()
    correction = _apply_status(
        db, correction, "APPLIED", "APPLIED", applied_by,
        {"category": correction.category},
    )
    from backend.observability import governance_metrics

    governance_metrics.record_correction_applied(correction.category)

    # Follow-up transactions (each independently idempotent / healable).
    #
    # Order matters. The invalidation is scoped to the corrected target (the
    # superseded ORIGINAL evidence) and marks every ACTIVE graph relationship
    # whose source OR target is that evidence. The `DERIVED_FROM` lineage edge
    # points NEW -> OLD, so the original is its target node: creating that edge
    # first makes it visible to the invalidation and the very provenance link
    # that records supersession is immediately marked INVALIDATED (§8/§9
    # require it to stay ACTIVE). Invalidate first, then record lineage, so
    # the edge survives as a durable provenance link. Both steps are
    # independently idempotent, so the ordering carries no retry risk.
    invalidation, reprocessing = _invalidate_for_correction(db, correction, applied_by)
    _ensure_evidence_lineage(db, correction)
    return correction, invalidation, reprocessing


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_correction(db: Session, correction_id: str):
    return _get_or_raise(db, correction_id)


def list_corrections(
    db: Session,
    *,
    project_id: str | None = None,
    project_ids: set[str] | None = None,
    status: str | None = None,
    category: str | None = None,
    target_id: str | None = None,
    requester_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list, int]:
    if status is not None and status not in STATUSES:
        raise ValueError(f"Unknown correction status: {status!r}")
    if category is not None and category not in CATEGORIES:
        raise ValueError(f"Unknown correction category: {category!r}")
    if limit < 1 or offset < 0:
        raise ValueError("Invalid pagination")
    if project_id is not None:
        project_id = _require_uuid(project_id, "project_id")
    if target_id is not None:
        target_id = _require_uuid(target_id, "target_id")
    if requester_id is not None:
        requester_id = _require_uuid(requester_id, "requester_id")
    query = correction_repo.list_query(
        db,
        project_id=project_id,
        project_ids=project_ids,
        status=status,
        category=category,
        target_id=target_id,
        requester_id=requester_id,
    )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return rows, total


def get_correction_history(db: Session, correction_id: str):
    correction = _get_or_raise(db, correction_id)
    events = correction_repo.events_for_correction(db, str(correction.id))
    return correction, events
