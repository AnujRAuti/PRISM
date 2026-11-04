"""BE-021 dispute service: authorized challenges with human governance.

A dispute never mutates its target and never determines truth, fraud, or
authenticity: resolution records human governance metadata only, using the
explicit vocabulary UPHELD / REJECTED / INCONCLUSIVE / INSUFFICIENT_EVIDENCE.
An UPHELD resolution triggers intelligence invalidation of the target's
downstream (BE-021 §13) through the governance service; every other
resolution leaves intelligence untouched.

Role separation (§12): the initiator of a dispute can never also act as
its reviewer/assigner/escalator/resolver — substantive decisions belong to
a different human. Withdrawal is the one initiator-only action.

Conventions (mirroring existing services): ``ValueError`` for invalid
input/semantic failures, ``LookupError`` for missing rows. Mutating
operations commit; idempotent retries are safe (§28).
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    DISPUTE_ACTIVE_STATUSES,
    DISPUTE_RESOLUTIONS,
    DISPUTE_STATUSES,
    DISPUTE_TARGET_TYPES,
    Dispute,
)
from backend.repositories import dispute as dispute_repo
from backend.services import audit_ledger as audit_service


logger = logging.getLogger(__name__)

TARGET_TYPES = frozenset(DISPUTE_TARGET_TYPES)
STATUSES = frozenset(DISPUTE_STATUSES)
ACTIVE_STATUSES = frozenset(DISPUTE_ACTIVE_STATUSES)
RESOLUTIONS = frozenset(DISPUTE_RESOLUTIONS)

# Explicit lifecycle matrix (§6): current status -> allowed next statuses.
# RESOLVED / REJECTED / WITHDRAWN are terminal; ESCALATED returns to
# UNDER_REVIEW only (§6: "Escalation may return to: UNDER_REVIEW").
TRANSITIONS: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"UNDER_REVIEW", "RESOLVED", "REJECTED", "ESCALATED", "WITHDRAWN"}),
    "UNDER_REVIEW": frozenset({"RESOLVED", "REJECTED", "ESCALATED", "WITHDRAWN"}),
    "ESCALATED": frozenset({"UNDER_REVIEW"}),
    "RESOLVED": frozenset(),
    "REJECTED": frozenset(),
    "WITHDRAWN": frozenset(),
}

# Domain event -> audit event mapping (BE-015). Only explicit vocabulary
# entries are emitted; the domain DisputeEvent rows keep full history.
DISPUTE_AUDIT_TYPES = {
    "CREATED": "DISPUTE_CREATED",
    "ASSIGNED": "DISPUTE_ASSIGNED",
    "REVIEW_STARTED": "DISPUTE_REVIEW_STARTED",
    "ESCALATED": "DISPUTE_ESCALATED",
    "RESOLVED": "DISPUTE_RESOLVED",
    "REJECTED": "DISPUTE_REJECTED",
    "WITHDRAWN": "DISPUTE_WITHDRAWN",
}

# Domain event -> notification type mapping (BE-018 §24). Payloads carry
# reference IDs only — never evidence content or free-text rationale.
DISPUTE_NOTIFICATION_TYPES = {
    "CREATED": "DISPUTE_CREATED",
    "ASSIGNED": "DISPUTE_ASSIGNED",
    "ESCALATED": "DISPUTE_ESCALATED",
    "RESOLVED": "DISPUTE_RESOLVED",
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
    """Explicitly validate a lifecycle transition (§6; never silent)."""
    if from_status not in TRANSITIONS:
        raise ValueError(f"Unknown dispute status: {from_status!r}")
    if to_status not in STATUSES:
        raise ValueError(f"Unknown dispute status: {to_status!r}")
    if to_status not in TRANSITIONS[from_status]:
        raise ValueError(f"Invalid transition: {from_status} -> {to_status}")


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------

def resolve_target(
    db: Session, target_type: str, target_id: str
) -> tuple[str | None, str | None]:
    """Validate the challenged target exists; return (project_id, error).

    ``project_id`` (where the target carries one) scopes the dispute for
    authorization; ``error`` is set when the target row is missing.
    """
    from backend.repositories import governance as governance_repo

    if target_type not in TARGET_TYPES:
        raise ValueError(f"Unknown dispute target type: {target_type!r}")
    target_id = _require_uuid(target_id, "target_id")
    row = governance_repo.get_target_row(db, target_type, target_id)
    if row is None:
        return None, f"{target_type} target not found: {target_id}"
    project_id = None
    if target_type == "EVIDENCE":
        project_id = str(row.project_id) if row.project_id else None
    elif target_type == "CLAIM":
        project_id = str(row.project_id) if row.project_id else None
    elif target_type == "REVIEW_CASE":
        project_id = str(row.project_id) if row.project_id else None
    elif target_type == "FUSION_ASSESSMENT":
        project_id = None  # assessments carry no project column
    elif target_type == "EVIDENCE_CLAIM_RELATIONSHIP":
        project_id = None  # scoping via endpoint nodes is enforced at API level
    elif target_type == "EXTERNAL_ASSERTION":
        project_id = None
    return project_id, None


# ---------------------------------------------------------------------------
# Audit / notification twins
# ---------------------------------------------------------------------------

def _audit_dispute_event(
    db: Session,
    dispute: Dispute,
    event_type: str,
    actor_id: str | None,
    action: str,
    extra_payload: dict | None = None,
) -> None:
    """Emit the audit twin of a dispute event in the same transaction."""
    audit_type = DISPUTE_AUDIT_TYPES.get(event_type)
    if audit_type is None:
        return
    audit_service.append_event(
        db,
        event_type=audit_type,
        action=action,
        resource_type="disputes",
        resource_id=dispute.id,
        actor_id=actor_id,
        project_id=str(dispute.project_id) if dispute.project_id else None,
        payload={
            "dispute_id": dispute.id,
            "target_type": dispute.target_type,
            "target_id": str(dispute.target_id),
            "status": dispute.status,
            **(extra_payload or {}),
        },
        source="dispute_service",
    )


def _emit_dispute_notification(
    db: Session, dispute: Dispute, event_type: str, metadata: dict | None
) -> None:
    """Emit the BE-018 notification twin (never fatal, IDs only, §24)."""
    try:
        from backend.services import notification as notif_service

        notif_type = DISPUTE_NOTIFICATION_TYPES.get(event_type)
        if notif_type is None:
            return
        payload: dict = {
            "dispute_id": str(dispute.id),
            "project_id": str(dispute.project_id) if dispute.project_id else None,
            "target_type": dispute.target_type,
            "target_id": str(dispute.target_id),
            "status": dispute.status,
            "resource_type": "dispute",
            "resource_id": str(dispute.id),
        }
        meta = metadata or {}
        if event_type == "ASSIGNED" and dispute.assigned_to:
            payload["assigned_to"] = str(dispute.assigned_to)
            payload["recipients"] = [str(dispute.assigned_to)]
        if event_type == "ESCALATED" and dispute.escalated_to:
            payload["escalated_to"] = str(dispute.escalated_to)
            payload["recipients"] = [str(dispute.escalated_to)]
        if event_type == "RESOLVED" and dispute.resolution:
            payload["resolution"] = dispute.resolution
        notif_service.emit_notification_event(
            db,
            event_type=notif_type,
            aggregate_type="DISPUTE",
            aggregate_id=str(dispute.id),
            payload=payload,
        )
    except Exception as exc:
        logger.warning(
            "Failed to emit notification for dispute %s event %s: %s",
            dispute.id, event_type, exc,
        )


# ---------------------------------------------------------------------------
# Shared workflow transition helper (review_case _apply pattern)
# ---------------------------------------------------------------------------

def _apply(
    db: Session,
    dispute: Dispute,
    to_status: str,
    event_type: str,
    actor_id: str | None,
    event_metadata: dict | None = None,
    **fields,
) -> Dispute:
    """Validate, mutate, record domain event + audit twin + notification, commit."""
    validate_transition(dispute.status, to_status)
    from_status = dispute.status
    for name, value in fields.items():
        setattr(dispute, name, value)
    dispute.status = to_status
    if to_status == "RESOLVED":
        dispute.resolved_at = utc_now()
    dispute_repo.insert_event(
        db,
        dispute_id=dispute.id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        metadata=event_metadata or {},
    )
    _audit_dispute_event(
        db,
        dispute,
        event_type,
        actor_id,
        action="transition"
        if to_status not in {"RESOLVED", "REJECTED", "WITHDRAWN"}
        else to_status.lower(),
        extra_payload={"from_status": from_status, "to_status": to_status},
    )
    _emit_dispute_notification(db, dispute, event_type, event_metadata)
    db.commit()
    db.refresh(dispute)
    return dispute


def _get_or_raise(db: Session, dispute_id: str) -> Dispute:
    dispute = dispute_repo.get_dispute(db, _require_uuid(dispute_id, "dispute_id"))
    if dispute is None:
        raise LookupError(f"Dispute not found: {dispute_id}")
    return dispute


def _lock_or_raise(db: Session, dispute_id: str) -> Dispute:
    dispute = dispute_repo.lock_dispute(db, _require_uuid(dispute_id, "dispute_id"))
    if dispute is None:
        raise LookupError(f"Dispute not found: {dispute_id}")
    return dispute


def _enforce_role_separation(dispute: Dispute, actor_id: str | None, action: str) -> None:
    """Requester may never be Reviewer/Resolver for the same dispute (§12)."""
    if actor_id is not None and str(actor_id) == str(dispute.initiator_id):
        raise ValueError(
            f"Role separation violation: the dispute initiator cannot {action} it"
        )


# ---------------------------------------------------------------------------
# Creation (idempotent per active target+initiator, §28)
# ---------------------------------------------------------------------------

def create_dispute(
    db: Session,
    *,
    target_type: str,
    target_id: str,
    initiator_id: str,
    reason: str,
    description: str | None = None,
) -> tuple[Dispute, bool]:
    """Create a dispute. Retrying an identical request returns the existing
    active dispute instead of a duplicate (§28)."""
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Unknown dispute target type: {target_type!r}")
    target_id = _require_uuid(target_id, "target_id")
    initiator_id = _require_uuid(initiator_id, "initiator_id")
    if not reason or not str(reason).strip():
        raise ValueError("Dispute reason is required")
    reason = str(reason).strip()
    if len(reason) > 256:
        raise ValueError("Dispute reason must be at most 256 characters")

    project_id, error = resolve_target(db, target_type, target_id)
    if error is not None:
        raise LookupError(error)

    existing = dispute_repo.active_dispute_for_target_initiator(
        db, target_type, target_id, initiator_id
    )
    if existing is not None:
        return existing, False

    try:
        dispute = dispute_repo.insert_dispute(
            db,
            target_type=target_type,
            target_id=target_id,
            project_id=project_id,
            initiator_id=initiator_id,
            reason=reason,
            description=description,
        )
        dispute_repo.insert_event(
            db,
            dispute_id=dispute.id,
            event_type="CREATED",
            from_status=None,
            to_status="OPEN",
            actor_id=initiator_id,
            metadata={"reason": reason},
        )
        _audit_dispute_event(
            db, dispute, "CREATED", initiator_id, "create",
            {"initiator_id": initiator_id},
        )
        _emit_dispute_notification(db, dispute, "CREATED", None)
        db.commit()
        from backend.observability import governance_metrics

        governance_metrics.record_dispute_created()
    except IntegrityError:
        # Concurrent duplicate creation: the partial-unique index picked a
        # winner; return it idempotently instead of failing the retry (§28).
        db.rollback()
        existing = dispute_repo.active_dispute_for_target_initiator(
            db, target_type, target_id, initiator_id
        )
        if existing is not None:
            return existing, False
        raise
    db.refresh(dispute)
    logger.info(
        "dispute created id=%s target=%s:%s", dispute.id, target_type, target_id
    )
    return dispute, True


# ---------------------------------------------------------------------------
# Workflow actions
# ---------------------------------------------------------------------------

def start_review(
    db: Session, dispute_id: str, *, actor_id: str | None = None, assigned_to: str | None = None
) -> Dispute:
    """OPEN/ESCALATED -> UNDER_REVIEW. Idempotent when already under review."""
    dispute = _lock_or_raise(db, dispute_id)
    _enforce_role_separation(dispute, actor_id, "review")
    if dispute.status == "UNDER_REVIEW":
        return dispute
    fields: dict = {}
    if assigned_to is not None:
        fields["assigned_to"] = _require_uuid(assigned_to, "assigned_to")
        fields["assigned_at"] = utc_now()
    return _apply(
        db, dispute, "UNDER_REVIEW", "REVIEW_STARTED", actor_id,
        {"assigned_to": str(assigned_to) if assigned_to else None},
        **fields,
    )


def assign_dispute(
    db: Session, dispute_id: str, *, assigned_to: str, actor_id: str | None = None
) -> Dispute:
    """Assign a reviewer to an active dispute (no status change; §6 keeps
    OPEN/UNDER_REVIEW/ESCALATED as the active band)."""
    dispute = _lock_or_raise(db, dispute_id)
    if dispute.status not in ACTIVE_STATUSES:
        raise ValueError(f"Only active disputes can be assigned (current: {dispute.status})")
    _enforce_role_separation(dispute, actor_id, "assign")
    assigned_to = _require_uuid(assigned_to, "assigned_to")
    if str(dispute.assigned_to) == assigned_to:
        return dispute
    dispute.assigned_to = assigned_to
    dispute.assigned_at = utc_now()
    dispute_repo.insert_event(
        db,
        dispute_id=dispute.id,
        event_type="ASSIGNED",
        from_status=dispute.status,
        to_status=dispute.status,
        actor_id=actor_id,
        metadata={"assigned_to": assigned_to},
    )
    _audit_dispute_event(
        db, dispute, "ASSIGNED", actor_id, "assign",
        {"assigned_to": assigned_to},
    )
    _emit_dispute_notification(db, dispute, "ASSIGNED", {"assigned_to": assigned_to})
    db.commit()
    db.refresh(dispute)
    return dispute


def escalate_dispute(
    db: Session,
    dispute_id: str,
    *,
    escalated_to: str,
    reason: str,
    actor_id: str | None = None,
) -> Dispute:
    """OPEN/UNDER_REVIEW -> ESCALATED; ESCALATED only returns via start_review."""
    dispute = _lock_or_raise(db, dispute_id)
    _enforce_role_separation(dispute, actor_id, "escalate")
    escalated_to = _require_uuid(escalated_to, "escalated_to")
    if not reason or not str(reason).strip():
        raise ValueError("Escalation reason is required")
    return _apply(
        db, dispute, "ESCALATED", "ESCALATED", actor_id,
        {"escalated_to": escalated_to, "reason": str(reason)},
        escalated_to=escalated_to,
        escalated_at=utc_now(),
        escalation_reason=str(reason),
    )


def resolve_dispute(
    db: Session,
    dispute_id: str,
    *,
    resolution: str,
    rationale: str,
    resolved_by: str | None = None,
    reprocess: bool = True,
) -> tuple[Dispute, object | None]:
    """Adjudicate: OPEN/UNDER_REVIEW -> RESOLVED with explicit vocabulary.

    Requires an authorized actor, an explicit resolution value, and a
    non-empty rationale (§7). Human decisions are append-only (§21): an
    already-RESOLVED dispute returns idempotently when the resolution
    matches, and re-adjudication with a *different* value is refused.

    An UPHELD resolution triggers intelligence invalidation of the target's
    downstream (§13) exactly once per dispute (§28), delegating to the
    governance service. Returns ``(dispute, invalidation_or_None)``.
    """
    dispute = _lock_or_raise(db, dispute_id)
    if resolution not in RESOLUTIONS:
        raise ValueError(f"Unknown resolution: {resolution!r}")
    if not rationale or not str(rationale).strip():
        raise ValueError("Resolution rationale is required")
    _enforce_role_separation(dispute, resolved_by, "resolve")

    if dispute.status == "RESOLVED":
        # Idempotent retry (§28) vs decision preservation (§21).
        if dispute.resolution == resolution:
            from backend.repositories import governance as governance_repo

            invalidation = governance_repo.invalidation_for_dispute(db, str(dispute.id))
            if invalidation is None and resolution == "UPHELD":
                # Crash healing: the original resolve committed the dispute
                # but died before the invalidation follow-up transaction.
                from backend.services import governance as governance_service

                invalidation, _ = governance_service.invalidate_target(
                    db,
                    target_type=dispute.target_type,
                    target_id=str(dispute.target_id),
                    cause="DISPUTE",
                    reason=f"Dispute {dispute.id} upheld: {dispute.resolution_rationale}",
                    invalidated_by=dispute.resolved_by,
                    dispute_id=str(dispute.id),
                    correction_id=None,
                    reprocess=reprocess,
                )
            return dispute, invalidation
        raise ValueError(
            "Dispute already resolved with a different resolution; "
            "human decisions are append-only historical records"
        )

    dispute = _apply(
        db, dispute, "RESOLVED", "RESOLVED", resolved_by,
        {"resolution": resolution, "rationale": str(rationale)},
        resolution=resolution,
        resolution_rationale=str(rationale),
        resolved_by=resolved_by,
    )
    from backend.observability import governance_metrics

    governance_metrics.record_dispute_resolved(resolution)

    invalidation = None
    if resolution == "UPHELD":
        # The challenge succeeded: downstream intelligence derived from the
        # target is invalidated and queued for reprocessing (§13, §17).
        from backend.services import governance as governance_service

        _, invalidation = governance_service.invalidate_target(
            db,
            target_type=dispute.target_type,
            target_id=str(dispute.target_id),
            cause="DISPUTE",
            reason=f"Dispute {dispute.id} upheld: {str(rationale)}",
            invalidated_by=resolved_by,
            dispute_id=str(dispute.id),
            correction_id=None,
            reprocess=reprocess,
        )
    return dispute, invalidation


def reject_dispute(
    db: Session, dispute_id: str, *, reason: str, actor_id: str | None = None
) -> Dispute:
    """Dismiss the challenge outright (OPEN/UNDER_REVIEW -> REJECTED).

    Distinct from a RESOLVED dispute with resolution REJECTED, which records
    a full adjudication. A dismissal carries no resolution metadata on the
    row (CHECK ck_dispute_resolution_status_consistent); the rationale lives
    in the append-only event history and audit twin (§21).
    """
    dispute = _lock_or_raise(db, dispute_id)
    _enforce_role_separation(dispute, actor_id, "reject")
    if not reason or not str(reason).strip():
        raise ValueError("Rejection reason is required")
    if dispute.status == "REJECTED":
        return dispute
    return _apply(
        db, dispute, "REJECTED", "REJECTED", actor_id, {"reason": str(reason)}
    )


def withdraw_dispute(
    db: Session, dispute_id: str, *, actor_id: str | None = None
) -> Dispute:
    """Initiator-only withdrawal from an active dispute (§6)."""
    dispute = _lock_or_raise(db, dispute_id)
    if dispute.status not in ACTIVE_STATUSES:
        raise ValueError(f"Only active disputes can be withdrawn (current: {dispute.status})")
    if actor_id is not None and str(actor_id) != str(dispute.initiator_id):
        raise ValueError("Only the dispute initiator may withdraw it")
    if dispute.status == "WITHDRAWN":
        return dispute
    return _apply(db, dispute, "WITHDRAWN", "WITHDRAWN", actor_id, {})


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_dispute(db: Session, dispute_id: str) -> Dispute:
    return _get_or_raise(db, dispute_id)


def list_disputes(
    db: Session,
    *,
    project_id: str | None = None,
    project_ids: set[str] | None = None,
    status: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    initiator_id: str | None = None,
    assigned_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Dispute], int]:
    if status is not None and status not in STATUSES:
        raise ValueError(f"Unknown dispute status: {status!r}")
    if target_type is not None and target_type not in TARGET_TYPES:
        raise ValueError(f"Unknown dispute target type: {target_type!r}")
    if limit < 1 or offset < 0:
        raise ValueError("Invalid pagination")
    if project_id is not None:
        project_id = _require_uuid(project_id, "project_id")
    if target_id is not None:
        target_id = _require_uuid(target_id, "target_id")
    if initiator_id is not None:
        initiator_id = _require_uuid(initiator_id, "initiator_id")
    if assigned_to is not None:
        assigned_to = _require_uuid(assigned_to, "assigned_to")
    query = dispute_repo.list_query(
        db,
        project_id=project_id,
        project_ids=project_ids,
        status=status,
        target_type=target_type,
        target_id=target_id,
        initiator_id=initiator_id,
        assigned_to=assigned_to,
    )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return rows, total


def get_dispute_history(db: Session, dispute_id: str) -> tuple[Dispute, list]:
    dispute = _get_or_raise(db, dispute_id)
    events = dispute_repo.events_for_dispute(db, str(dispute.id))
    return dispute, events
