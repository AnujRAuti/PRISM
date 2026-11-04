"""BE-014 evidence-request repository: persistence and queries only.

Lifecycle rules, fulfillment math, and scope validation live in
``backend.services.evidence_request``.
"""

from datetime import datetime, timezone

from sqlalchemy import false
from sqlalchemy.orm import Session

from backend.db.models import (
    EvidenceRequest,
    EvidenceRequestEvent,
    EvidenceRequestItem,
)


def insert_request(db: Session, **fields) -> EvidenceRequest:
    row = EvidenceRequest(**fields)
    db.add(row)
    db.flush()
    return row


def get_request(db: Session, request_id: str) -> EvidenceRequest | None:
    return db.query(EvidenceRequest).filter(EvidenceRequest.id == request_id).one_or_none()


def insert_item(db: Session, **fields) -> EvidenceRequestItem:
    row = EvidenceRequestItem(**fields)
    # Explicit per-insert timestamps (same rationale as events): same-commit
    # items must keep creation order so slot filling is deterministic.
    if row.created_at is None:
        row.created_at = datetime.now(timezone.utc)
    db.add(row)
    db.flush()
    return row


def get_item(db: Session, item_id: str) -> EvidenceRequestItem | None:
    return db.query(EvidenceRequestItem).filter(EvidenceRequestItem.id == item_id).one_or_none()


def items_for_request(db: Session, request_id: str) -> list[EvidenceRequestItem]:
    return (
        db.query(EvidenceRequestItem)
        .filter(EvidenceRequestItem.request_id == request_id)
        .order_by(EvidenceRequestItem.created_at, EvidenceRequestItem.id)
        .all()
    )


def find_item_link(
    db: Session, request_id: str, evidence_id: str
) -> EvidenceRequestItem | None:
    return (
        db.query(EvidenceRequestItem)
        .filter(
            EvidenceRequestItem.request_id == request_id,
            EvidenceRequestItem.evidence_id == evidence_id,
        )
        .order_by(EvidenceRequestItem.created_at, EvidenceRequestItem.id)
        .first()
    )


def insert_event(
    db: Session,
    *,
    request_id: str,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    actor_id: str | None,
    metadata: dict,
) -> EvidenceRequestEvent:
    row = EvidenceRequestEvent(
        request_id=request_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        event_metadata=metadata,
        # Explicit per-insert timestamps: PG now() is stable per
        # transaction, which would leave same-commit events unordered
        # under the (created_at, id) ordering (random UUIDv4 ids).
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def events_for_request(db: Session, request_id: str) -> list[EvidenceRequestEvent]:
    return (
        db.query(EvidenceRequestEvent)
        .filter(EvidenceRequestEvent.request_id == request_id)
        .order_by(EvidenceRequestEvent.created_at, EvidenceRequestEvent.id)
        .all()
    )


def list_query(
    db: Session,
    *,
    project_id: str | None,
    project_ids: set[str] | None,
    review_case_id: str | None,
    status: str | None,
    priority: str | None,
    requester_id: str | None,
    recipient_id: str | None,
    due_before=None,
    due_after=None,
):
    query = db.query(EvidenceRequest)
    if project_id is not None:
        query = query.filter(EvidenceRequest.project_id == project_id)
    if project_ids is not None:
        query = query.filter(EvidenceRequest.project_id.in_(project_ids)) if project_ids else query.filter(false())
    if review_case_id is not None:
        query = query.filter(EvidenceRequest.review_case_id == review_case_id)
    if status is not None:
        query = query.filter(EvidenceRequest.status == status)
    if priority is not None:
        query = query.filter(EvidenceRequest.priority == priority)
    if requester_id is not None:
        query = query.filter(EvidenceRequest.requester_id == requester_id)
    if recipient_id is not None:
        query = query.filter(EvidenceRequest.recipient_id == recipient_id)
    if due_before is not None:
        query = query.filter(
            EvidenceRequest.due_at.is_not(None), EvidenceRequest.due_at < due_before
        )
    if due_after is not None:
        query = query.filter(
            EvidenceRequest.due_at.is_not(None), EvidenceRequest.due_at > due_after
        )
    return query.order_by(EvidenceRequest.created_at.desc(), EvidenceRequest.id.desc())
