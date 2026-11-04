"""BE-014 evidence-request service: workflow, linking, fulfillment.

A request asks for evidence; it is never evidence itself, and fulfillment
never implies truth, support, or contradiction. Requested evidence enters
the existing BE-003 ingestion pipeline with identical validation and is
never marked trusted. Review cases are never mutated here.

Conventions: ``ValueError`` for invalid input/semantic failures,
``LookupError`` for missing rows. Valid transitions emit exactly one
event; invalid ones mutate nothing and emit nothing.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    EVIDENCE_REQUEST_ITEM_STATUSES,
    EVIDENCE_REQUEST_PRIORITIES,
    EVIDENCE_REQUEST_STATUSES,
    Activity,
    Claim,
    Evidence,
    EvidenceRequest,
    Project,
    ReviewCase,
)
from backend.repositories import evidence_request as request_repo
from backend.services import audit_ledger as audit_service
from backend.services.evidence_ingestion import ingest_evidence


logger = logging.getLogger(__name__)

STATUSES = frozenset(EVIDENCE_REQUEST_STATUSES)
PRIORITIES = frozenset(EVIDENCE_REQUEST_PRIORITIES)
ITEM_STATUSES = frozenset(EVIDENCE_REQUEST_ITEM_STATUSES)

LINKABLE_STATUSES = frozenset({"OPEN", "ACKNOWLEDGED", "PARTIALLY_FULFILLED"})

# Domain event -> audit event mapping. Only explicit vocabulary entries are
# emitted; item-level receipt events stay domain history (incremental).
REQUEST_AUDIT_TYPES = {
    "REQUEST_CREATED": "EVIDENCE_REQUEST_CREATED",
    "REQUEST_ISSUED": "EVIDENCE_REQUEST_ISSUED",
    "REQUEST_ACKNOWLEDGED": "EVIDENCE_REQUEST_ACKNOWLEDGED",
    "FULFILLED": "EVIDENCE_REQUEST_FULFILLED",
    "DECLINED": "EVIDENCE_REQUEST_DECLINED",
    "CANCELLED": "EVIDENCE_REQUEST_CANCELLED",
    "EXPIRED": "EVIDENCE_REQUEST_EXPIRED",
}


def _audit_request_event(
    db: Session, request, event_type: str, actor_id: str | None, action: str
) -> None:
    """Emit the audit twin of a request event in the same transaction."""
    audit_type = REQUEST_AUDIT_TYPES.get(event_type)
    if audit_type is None:
        return
    audit_service.append_event(
        db,
        event_type=audit_type,
        action=action,
        resource_type="evidence_requests",
        resource_id=request.id,
        actor_id=actor_id,
        project_id=str(request.project_id) if request.project_id else None,
        payload={"evidence_request_id": request.id, "status": request.status,
                 "review_case_id": str(request.review_case_id)
                 if request.review_case_id else None},
        source="evidence_request_service",
    )


def _emit_request_notification(
    db: Session, request, event_type: str, metadata: dict | None = None
) -> None:
    try:
        from backend.services import notification as notif_service

        meta = metadata or {}
        notif_type = None
        payload = {
            "request_id": str(request.id),
            "project_id": str(request.project_id) if request.project_id else None,
            "resource_type": "evidence_request",
            "resource_id": str(request.id),
        }
        if event_type == "REQUEST_ISSUED" and request.recipient_id:
            notif_type = "EVIDENCE_REQUEST_ISSUED"
            payload["recipient_id"] = str(request.recipient_id)
            payload["priority"] = getattr(request, "priority", "NORMAL")
        elif event_type == "REQUEST_ACKNOWLEDGED" and request.requester_id:
            notif_type = "EVIDENCE_REQUEST_ACKNOWLEDGED"
            payload["created_by"] = str(request.requester_id)
        elif event_type == "PARTIAL_FULFILLMENT" and request.requester_id:
            notif_type = "EVIDENCE_REQUEST_PARTIALLY_FULFILLED"
            payload["created_by"] = str(request.requester_id)
        elif event_type == "FULFILLED" and request.requester_id:
            notif_type = "EVIDENCE_REQUEST_FULFILLED"
            payload["created_by"] = str(request.requester_id)
        elif event_type == "DECLINED" and request.requester_id:
            notif_type = "EVIDENCE_REQUEST_DECLINED"
            payload["created_by"] = str(request.requester_id)
            payload["reason"] = meta.get("reason", "Declined")
        elif event_type == "EXPIRED" and request.requester_id:
            notif_type = "EVIDENCE_REQUEST_EXPIRED"
            payload["created_by"] = str(request.requester_id)

        if notif_type:
            notif_service.emit_notification_event(
                db,
                event_type=notif_type,
                aggregate_type="EVIDENCE_REQUEST",
                aggregate_id=str(request.id),
                payload=payload,
            )
    except Exception as exc:
        logger.warning(
            "Failed to emit notification for request %s event %s: %s", request.id, event_type, exc
        )


def _emit_request_webhook(
    db: Session, request, event_type: str, metadata: dict | None = None
) -> None:
    try:
        from backend.services import webhook as webhook_service

        wh_type = None
        if event_type == "REQUEST_ISSUED":
            wh_type = "evidence_request.issued"
        elif event_type == "FULFILLED":
            wh_type = "evidence_request.fulfilled"
        elif event_type == "DECLINED":
            wh_type = "evidence_request.declined"
        elif event_type == "EXPIRED":
            wh_type = "evidence_request.expired"

        if wh_type:
            webhook_service.enqueue_webhook_event(
                db,
                event_type=wh_type,
                aggregate_type="EVIDENCE_REQUEST",
                aggregate_id=str(request.id),
                project_id=str(request.project_id) if request.project_id else None,
                data={
                    "request_id": str(request.id),
                    "status": request.status,
                },
            )
    except Exception as exc:
        logger.warning(
            "Failed to emit webhook for request %s event %s: %s", request.id, event_type, exc
        )



TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"OPEN", "CANCELLED"}),
    "OPEN": frozenset({"ACKNOWLEDGED", "DECLINED", "EXPIRED", "CANCELLED", "FULFILLED",
                        "PARTIALLY_FULFILLED"}),
    "ACKNOWLEDGED": frozenset({"DECLINED", "EXPIRED", "CANCELLED", "FULFILLED",
                               "PARTIALLY_FULFILLED"}),
    "PARTIALLY_FULFILLED": frozenset({"FULFILLED", "CANCELLED"}),
    "FULFILLED": frozenset(),
    "DECLINED": frozenset(),
    "EXPIRED": frozenset(),
    "CANCELLED": frozenset(),
}

# Item lifecycle (per slot).
ITEM_TRANSITIONS: dict[str, frozenset[str]] = {
    "REQUESTED": frozenset({"RECEIVED"}),
    "RECEIVED": frozenset({"ACCEPTED_FOR_REQUEST", "REJECTED_FOR_REQUEST"}),
    "ACCEPTED_FOR_REQUEST": frozenset(),
    "REJECTED_FOR_REQUEST": frozenset(),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_uuid(value: str, label: str) -> str:
    from uuid import UUID

    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error


def _optional_uuid(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _require_uuid(value, label)


# ---------------------------------------------------------------------------
# Pure rules (unit-testable without a database)
# ---------------------------------------------------------------------------


def validate_transition(from_status: str, to_status: str) -> None:
    """Reject any lifecycle move outside the explicit matrix."""
    if from_status not in STATUSES:
        raise ValueError(f"Unknown request status: {from_status!r}")
    if to_status not in STATUSES:
        raise ValueError(f"Unknown request status: {to_status!r}")
    if to_status not in TRANSITIONS.get(from_status, frozenset()):
        raise ValueError(f"Invalid transition: {from_status} -> {to_status}")


def validate_item_transition(from_status: str, to_status: str) -> None:
    if from_status not in ITEM_STATUSES:
        raise ValueError(f"Unknown item status: {from_status!r}")
    if to_status not in ITEM_STATUSES:
        raise ValueError(f"Unknown item status: {to_status!r}")
    if to_status not in ITEM_TRANSITIONS.get(from_status, frozenset()):
        raise ValueError(f"Invalid item transition: {from_status} -> {to_status}")


def normalize_due_at(due_at: datetime | None) -> datetime | None:
    """Due dates must be timezone-aware; normalized to UTC, never invented."""
    if due_at is None:
        return None
    if not isinstance(due_at, datetime):
        raise ValueError("due_at must be a datetime")
    if due_at.tzinfo is None:
        raise ValueError("due_at must be timezone-aware (naive timestamps rejected)")
    return due_at.astimezone(timezone.utc)


def fulfillment_state(items: list) -> str | None:
    """Deterministic fulfillment from item rows (None = no status change).

    FULFILLED requires every required item ACCEPTED; PARTIALLY_FULFILLED
    requires at least one ACCEPTED with a required item still unresolved.
    REJECTED items never count as fulfilled.
    """
    required = [item for item in items if _is_required(item)]
    if not required:
        return None
    accepted = [item for item in required if _item_status(item) == "ACCEPTED_FOR_REQUEST"]
    if len(accepted) == len(required):
        return "FULFILLED"
    if accepted:
        return "PARTIALLY_FULFILLED"
    return None


def _is_required(item) -> bool:
    return bool(item.required if hasattr(item, "required") else item.get("required", True))


def _item_status(item) -> str:
    status = item.item_status if hasattr(item, "item_status") else item.get("item_status")
    return str(status)


def expiration_eligible(status: str, due_at: datetime | None, now: datetime) -> bool:
    """Eligible only for OPEN/ACKNOWLEDGED with a past due date (pure)."""
    if status not in ("OPEN", "ACKNOWLEDGED") or due_at is None:
        return False
    current = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    return due_at <= current


def check_scope_consistency(resolved: dict[str, str | None]) -> None:
    """Pure domain-consistency check over resolved project ids.

    ``resolved`` maps scope roles (project/claim/activity/evidence/case) to
    their owning project id (or None when unscoped). Any two known projects
    must agree — no silent cross-project association.
    """
    known = {role: project for role, project in resolved.items() if project is not None}
    if len(set(known.values())) > 1:
        raise ValueError(
            "Scope inconsistency: "
            + ", ".join(f"{role} in project {project}" for role, project in sorted(known.items()))
        )


# ---------------------------------------------------------------------------
# Scope resolution (read-only)
# ---------------------------------------------------------------------------


def _resolve_scope(
    db: Session,
    *,
    project_id: str | None,
    activity_id: str | None,
    claim_id: str | None,
    evidence_id: str | None,
    review_case_id: str | None,
) -> dict:
    """Load scope rows, inherit the case project when unset, check consistency."""
    if review_case_id is not None:
        case = db.query(ReviewCase).filter(ReviewCase.id == review_case_id).one_or_none()
        if case is None:
            raise LookupError(f"Review case not found: {review_case_id}")
    else:
        case = None
    project = activity = claim = evidence = None
    if project_id is not None:
        project = db.query(Project).filter(Project.id == project_id).one_or_none()
        if project is None:
            raise LookupError(f"Project not found: {project_id}")
    if activity_id is not None:
        activity = db.query(Activity).filter(Activity.id == activity_id).one_or_none()
        if activity is None:
            raise LookupError(f"Activity not found: {activity_id}")
    if claim_id is not None:
        claim = db.query(Claim).filter(Claim.id == claim_id).one_or_none()
        if claim is None:
            raise LookupError(f"Claim not found: {claim_id}")
    if evidence_id is not None:
        evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
        if evidence is None:
            raise LookupError(f"Evidence not found: {evidence_id}")
    resolved = {
        "project": str(project.id) if project else None,
        "activity": str(activity.project_id) if activity else None,
        "claim": str(claim.project_id) if claim else None,
        "evidence": str(evidence.project_id) if evidence and evidence.project_id else None,
        "case": str(case.project_id) if case and case.project_id else None,
    }
    check_scope_consistency(resolved)
    effective_project = resolved["project"] or resolved["case"]
    return {
        "case": case,
        "project_id": effective_project,
        "activity_id": activity_id,
        "claim_id": claim_id,
        "evidence_id": evidence_id,
    }


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def create_request(
    db: Session,
    *,
    review_case_id: str,
    recipient_id: str,
    instructions: str,
    items: list[dict],
    requester_id: str | None = None,
    due_at: datetime | None = None,
    priority: str = "NORMAL",
    project_id: str | None = None,
    activity_id: str | None = None,
    claim_id: str | None = None,
    evidence_id: str | None = None,
    issue: bool = True,
) -> EvidenceRequest:
    """Create a request with its item slots (DRAFT, or OPEN when issued)."""
    review_case_id = _require_uuid(review_case_id, "review_case_id")
    recipient_id = _require_uuid(recipient_id, "recipient_id")
    requester_id = _optional_uuid(requester_id, "requester_id")
    project_id = _optional_uuid(project_id, "project_id")
    activity_id = _optional_uuid(activity_id, "activity_id")
    claim_id = _optional_uuid(claim_id, "claim_id")
    evidence_id = _optional_uuid(evidence_id, "evidence_id")
    if instructions is None or not str(instructions).strip():
        raise ValueError("Request instructions are required and must not be empty")
    if not isinstance(items, list) or not items:
        raise ValueError("At least one request item is required")
    if priority not in PRIORITIES:
        raise ValueError(f"Unknown request priority: {priority!r}")
    due_at = normalize_due_at(due_at)
    scope = _resolve_scope(
        db, project_id=project_id, activity_id=activity_id, claim_id=claim_id,
        evidence_id=evidence_id, review_case_id=review_case_id,
    )
    status = "OPEN" if issue else "DRAFT"
    request = request_repo.insert_request(
        db,
        review_case_id=review_case_id,
        project_id=scope["project_id"],
        activity_id=activity_id,
        claim_id=claim_id,
        evidence_id=evidence_id,
        requester_id=requester_id,
        recipient_id=recipient_id,
        instructions=str(instructions).strip(),
        due_at=due_at,
        priority=priority,
        status=status,
    )
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Request items must be mappings")
        request_repo.insert_item(
            db,
            request_id=request.id,
            description=item.get("description"),
            required=bool(item.get("required", True)),
            item_status="REQUESTED",
        )
    request_repo.insert_event(
        db, request_id=request.id, event_type="REQUEST_CREATED", from_status=None,
        to_status="DRAFT", actor_id=requester_id,
        metadata={"item_count": len(items)},
    )
    _audit_request_event(db, request, "REQUEST_CREATED", requester_id, "create")
    if issue:
        request_repo.insert_event(
            db, request_id=request.id, event_type="REQUEST_ISSUED", from_status="DRAFT",
            to_status="OPEN", actor_id=requester_id, metadata={},
        )
        _audit_request_event(db, request, "REQUEST_ISSUED", requester_id, "transition")
        _emit_request_notification(db, request, "REQUEST_ISSUED")
        _emit_request_webhook(db, request, "REQUEST_ISSUED")
    db.commit()
    db.refresh(request)
    logger.info("evidence request created request_id=%s status=%s", request.id, status)
    return request


def get_request(db: Session, request_id: str) -> EvidenceRequest:
    request_id = _require_uuid(request_id, "request_id")
    request = request_repo.get_request(db, request_id)
    if request is None:
        raise LookupError(f"Evidence request not found: {request_id}")
    return request


def list_requests(
    db: Session,
    *,
    project_id: str | None = None,
    review_case_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    requester_id: str | None = None,
    recipient_id: str | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    project_ids: set[str] | None = None,
):
    if status is not None and status not in STATUSES:
        raise ValueError(f"Unknown request status: {status!r}")
    if priority is not None and priority not in PRIORITIES:
        raise ValueError(f"Unknown request priority: {priority!r}")
    if limit < 1 or offset < 0:
        raise ValueError("Invalid pagination")
    query = request_repo.list_query(
        db,
        project_id=_optional_uuid(project_id, "project_id"),
        project_ids=project_ids,
        review_case_id=_optional_uuid(review_case_id, "review_case_id"),
        status=status,
        priority=priority,
        requester_id=_optional_uuid(requester_id, "requester_id"),
        recipient_id=_optional_uuid(recipient_id, "recipient_id"),
        due_before=normalize_due_at(due_before),
        due_after=normalize_due_at(due_after),
    )
    return query.offset(offset).limit(limit).all(), query.count()


def request_history(db: Session, request_id: str) -> list:
    request = get_request(db, request_id)
    return request_repo.events_for_request(db, request.id)


def request_items(db: Session, request_id: str) -> list:
    request = get_request(db, request_id)
    return request_repo.items_for_request(db, request.id)


# ---------------------------------------------------------------------------
# Lifecycle actions (each valid move emits exactly one event)
# ---------------------------------------------------------------------------


def _apply(
    db: Session,
    request: EvidenceRequest,
    to_status: str,
    event_type: str,
    actor_id: str | None,
    event_metadata: dict | None = None,
) -> EvidenceRequest:
    validate_transition(request.status, to_status)
    from_status = request.status
    request.status = to_status
    request_repo.insert_event(
        db, request_id=request.id, event_type=event_type, from_status=from_status,
        to_status=to_status, actor_id=actor_id, metadata=event_metadata or {},
    )
    _audit_request_event(db, request, event_type, actor_id, "transition")
    _emit_request_notification(db, request, event_type, event_metadata)
    _emit_request_webhook(db, request, event_type, event_metadata)
    db.commit()
    db.refresh(request)
    return request


def issue_request(db: Session, request_id: str, actor_id: str | None = None):
    request = get_request(db, request_id)
    return _apply(db, request, "OPEN", "REQUEST_ISSUED",
                  _optional_uuid(actor_id, "actor_id"))


def acknowledge_request(db: Session, request_id: str, actor_id: str | None = None):
    """Idempotent: re-acknowledging returns the request with no new event."""
    request = get_request(db, request_id)
    if request.status == "ACKNOWLEDGED":
        return request
    return _apply(db, request, "ACKNOWLEDGED", "REQUEST_ACKNOWLEDGED",
                  _optional_uuid(actor_id, "actor_id"))


def decline_request(db: Session, request_id: str, reason: str, actor_id: str | None = None):
    if reason is None or not str(reason).strip():
        raise ValueError("Decline reason is required and must not be empty")
    request = get_request(db, request_id)
    return _apply(db, request, "DECLINED", "DECLINED",
                  _optional_uuid(actor_id, "actor_id"),
                  {"reason": str(reason).strip()})


def cancel_request(db: Session, request_id: str, actor_id: str | None = None):
    request = get_request(db, request_id)
    return _apply(db, request, "CANCELLED", "CANCELLED",
                  _optional_uuid(actor_id, "actor_id"))


def expire_request(db: Session, request_id: str, actor_id: str | None = None,
                   now: datetime | None = None):
    """Explicit deterministic expiration (no background scheduler in V1)."""
    request = get_request(db, request_id)
    if request.status == "EXPIRED":
        return request
    moment = now if now is not None else utc_now()
    if not expiration_eligible(request.status, request.due_at, moment):
        raise ValueError(
            f"Request is not eligible for expiration (status={request.status}, "
            f"due_at={request.due_at.isoformat() if request.due_at else None})"
        )
    return _apply(db, request, "EXPIRED", "EXPIRED",
                  _optional_uuid(actor_id, "actor_id"),
                  {"due_at": request.due_at.isoformat()})


# ---------------------------------------------------------------------------
# Evidence linking and fulfillment
# ---------------------------------------------------------------------------


def _refresh_fulfillment(
    db: Session, request: EvidenceRequest, actor_id: str | None = None
) -> EvidenceRequest:
    """Recompute fulfillment; emit a status event only on actual change."""
    if request.status in ("FULFILLED", "DECLINED", "EXPIRED", "CANCELLED", "DRAFT"):
        return request
    items = request_repo.items_for_request(db, request.id)
    target = fulfillment_state(items)
    if target is None or target == request.status:
        return request
    validate_transition(request.status, target)
    from_status = request.status
    request.status = target
    event_type = "FULFILLED" if target == "FULFILLED" else "PARTIAL_FULFILLMENT"
    request_repo.insert_event(
        db, request_id=request.id, event_type=event_type,
        from_status=from_status, to_status=target, actor_id=actor_id, metadata={},
    )
    _audit_request_event(db, request, event_type, actor_id, "transition")
    _emit_request_notification(db, request, event_type)
    _emit_request_webhook(db, request, event_type)
    return request


def link_evidence(
    db: Session, request_id: str, evidence_id: str,
    actor_id: str | None = None, item_id: str | None = None,
):
    """Link existing evidence: fills an open slot, RECEIVED, recompute status.

    Idempotent: re-linking already-linked evidence returns the existing
    item without new rows or events. Never copies files; never judges.
    """
    request = get_request(db, request_id)
    evidence_id = _require_uuid(evidence_id, "evidence_id")
    actor_id = _optional_uuid(actor_id, "actor_id")
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
    if evidence is None:
        raise LookupError(f"Evidence not found: {evidence_id}")
    if request.status not in LINKABLE_STATUSES:
        raise ValueError(f"Request in status {request.status} cannot accept evidence")
    if (
        request.project_id is not None
        and evidence.project_id is not None
        and str(evidence.project_id) != str(request.project_id)
    ):
        raise ValueError(
            "Scope inconsistency: evidence belongs to a different project than the request"
        )
    existing = request_repo.find_item_link(db, request.id, evidence_id)
    if existing is not None:
        return existing, False
    if item_id is not None:
        item = request_repo.get_item(db, _require_uuid(item_id, "item_id"))
        if item is None or str(item.request_id) != str(request.id):
            raise LookupError(f"Request item not found: {item_id}")
        if item.item_status != "REQUESTED" or item.evidence_id is not None:
            raise ValueError("Request item is not open for linking")
        slot = item
    else:
        open_slots = [
            item for item in request_repo.items_for_request(db, request.id)
            if item.item_status == "REQUESTED" and item.evidence_id is None
        ]
        if not open_slots:
            raise ValueError("Request has no open items to link evidence to")
        slot = open_slots[0]
    try:
        slot.evidence_id = evidence_id
        slot.item_status = "RECEIVED"
        slot.linked_at = utc_now()
        slot.linked_by = actor_id
        request_repo.insert_event(
            db, request_id=request.id, event_type="EVIDENCE_LINKED",
            from_status=request.status, to_status=request.status, actor_id=actor_id,
            metadata={"item_id": slot.id, "evidence_id": evidence_id},
        )
        _refresh_fulfillment(db, request, actor_id)
        db.commit()
    except IntegrityError:
        # Concurrent duplicate link: the winner is canonical.
        db.rollback()
        existing = request_repo.find_item_link(db, request.id, evidence_id)
        if existing is not None:
            return existing, False
        raise
    db.refresh(slot)
    db.refresh(request)
    return slot, True


def accept_item(db: Session, request_id: str, item_id: str, actor_id: str | None = None):
    """Reviewer accepts received evidence for this item (operational only)."""
    request = get_request(db, request_id)
    item = request_repo.get_item(db, _require_uuid(item_id, "item_id"))
    if item is None or str(item.request_id) != str(request.id):
        raise LookupError(f"Request item not found: {item_id}")
    validate_item_transition(item.item_status, "ACCEPTED_FOR_REQUEST")
    item.item_status = "ACCEPTED_FOR_REQUEST"
    actor = _optional_uuid(actor_id, "actor_id")
    request_repo.insert_event(
        db, request_id=request.id, event_type="ITEM_ACCEPTED",
        from_status=request.status, to_status=request.status,
        actor_id=actor, metadata={"item_id": item.id},
    )
    _refresh_fulfillment(db, request, actor)
    db.commit()
    db.refresh(item)
    db.refresh(request)
    return item


def reject_item(db: Session, request_id: str, item_id: str,
                actor_id: str | None = None, notes: str | None = None):
    """Reviewer rejects received evidence for this item (evidence stays valid)."""
    request = get_request(db, request_id)
    item = request_repo.get_item(db, _require_uuid(item_id, "item_id"))
    if item is None or str(item.request_id) != str(request.id):
        raise LookupError(f"Request item not found: {item_id}")
    validate_item_transition(item.item_status, "REJECTED_FOR_REQUEST")
    item.item_status = "REJECTED_FOR_REQUEST"
    if notes is not None:
        item.notes = str(notes)
    actor = _optional_uuid(actor_id, "actor_id")
    request_repo.insert_event(
        db, request_id=request.id, event_type="ITEM_REJECTED",
        from_status=request.status, to_status=request.status,
        actor_id=actor, metadata={"item_id": item.id},
    )
    _refresh_fulfillment(db, request, actor)
    db.commit()
    db.refresh(item)
    db.refresh(request)
    return item


def submit_evidence(
    db: Session, request_id: str, data: bytes, filename: str,
    content_type: str | None, actor_id: str | None = None,
):
    """Upload new evidence through the existing pipeline, then link it.

    Validation/storage/DB behavior is exactly BE-003's: invalid uploads
    raise (never become linked), and linked evidence is quarantined like
    any other — requested provenance is recorded on the link, never as
    trust in the evidence row.
    """
    request = get_request(db, request_id)
    if request.status not in LINKABLE_STATUSES:
        raise ValueError(f"Request in status {request.status} cannot accept evidence")
    evidence = ingest_evidence(data, filename, content_type, db, actor_id=actor_id)
    # Ingestion already committed: if linking below fails, the evidence
    # remains valid quarantined evidence (never deleted silently).
    item, created = link_evidence(db, request.id, evidence.id, actor_id)
    return evidence, item, created
