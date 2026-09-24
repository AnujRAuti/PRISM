"""BE-021 correction repository: persistence and deterministic queries only.

Lifecycle rules, role separation, and application semantics live in
``backend.services.correction``. Row-level locking exists for §29
concurrency (approval must not race with application).
"""

from sqlalchemy import false
from sqlalchemy.orm import Session

from backend.db.models import CorrectionEvent, CorrectionRequest


def insert_correction(
    db: Session,
    *,
    target_type: str,
    target_id: str,
    project_id: str | None,
    category: str,
    requested_change: dict,
    reason: str,
    requester_id: str,
) -> CorrectionRequest:
    row = CorrectionRequest(
        target_type=target_type,
        target_id=target_id,
        project_id=project_id,
        category=category,
        requested_change=requested_change,
        reason=reason,
        requester_id=requester_id,
        status="REQUESTED",
    )
    db.add(row)
    db.flush()
    return row


def get_correction(db: Session, correction_id: str) -> CorrectionRequest | None:
    return (
        db.query(CorrectionRequest)
        .filter(CorrectionRequest.id == correction_id)
        .one_or_none()
    )


def lock_correction(db: Session, correction_id: str) -> CorrectionRequest | None:
    """SELECT ... FOR UPDATE so concurrent approvers/appliers serialize."""
    return (
        db.query(CorrectionRequest)
        .filter(CorrectionRequest.id == correction_id)
        .with_for_update()
        .one_or_none()
    )


def list_query(
    db: Session,
    *,
    project_id: str | None,
    project_ids: set[str] | None,
    status: str | None,
    category: str | None,
    target_id: str | None,
    requester_id: str | None,
):
    query = db.query(CorrectionRequest)
    if project_id is not None:
        query = query.filter(CorrectionRequest.project_id == project_id)
    if project_ids is not None:
        query = (
            query.filter(CorrectionRequest.project_id.in_(project_ids))
            if project_ids
            else query.filter(false())
        )
    if status is not None:
        query = query.filter(CorrectionRequest.status == status)
    if category is not None:
        query = query.filter(CorrectionRequest.category == category)
    if target_id is not None:
        query = query.filter(CorrectionRequest.target_id == target_id)
    if requester_id is not None:
        query = query.filter(CorrectionRequest.requester_id == requester_id)
    return query.order_by(CorrectionRequest.created_at.desc(), CorrectionRequest.id.desc())


def insert_event(
    db: Session,
    *,
    correction_id: str,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    actor_id: str | None,
    metadata: dict,
) -> CorrectionEvent:
    row = CorrectionEvent(
        correction_id=correction_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        event_metadata=metadata,
    )
    db.add(row)
    db.flush()
    return row


def events_for_correction(db: Session, correction_id: str) -> list[CorrectionEvent]:
    return (
        db.query(CorrectionEvent)
        .filter(CorrectionEvent.correction_id == correction_id)
        .order_by(CorrectionEvent.created_at.asc(), CorrectionEvent.id.asc())
        .all()
    )
