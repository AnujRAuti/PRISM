"""BE-021 dispute repository: persistence and deterministic queries only.

Lifecycle rules, idempotency policy, and governance actions live in
``backend.services.dispute``. Row-level locking helpers exist for §29
concurrency (two reviewers must never resolve the same dispute).
"""

from sqlalchemy import false
from sqlalchemy.orm import Session

from backend.db.models import Dispute, DisputeEvent


def insert_dispute(
    db: Session,
    *,
    target_type: str,
    target_id: str,
    project_id: str | None,
    initiator_id: str,
    reason: str,
    description: str | None,
) -> Dispute:
    row = Dispute(
        target_type=target_type,
        target_id=target_id,
        project_id=project_id,
        initiator_id=initiator_id,
        reason=reason,
        description=description,
        status="OPEN",
    )
    db.add(row)
    db.flush()
    return row


def get_dispute(db: Session, dispute_id: str) -> Dispute | None:
    return db.query(Dispute).filter(Dispute.id == dispute_id).one_or_none()


def lock_dispute(db: Session, dispute_id: str) -> Dispute | None:
    """SELECT ... FOR UPDATE so concurrent resolvers serialize (§29)."""
    return (
        db.query(Dispute)
        .filter(Dispute.id == dispute_id)
        .with_for_update()
        .one_or_none()
    )


def active_dispute_for_target_initiator(
    db: Session, target_type: str, target_id: str, initiator_id: str
) -> Dispute | None:
    """One active challenge per (target, initiator) — idempotency window."""
    return (
        db.query(Dispute)
        .filter(
            Dispute.target_type == target_type,
            Dispute.target_id == target_id,
            Dispute.initiator_id == initiator_id,
            Dispute.status.in_(("OPEN", "UNDER_REVIEW", "ESCALATED")),
        )
        .order_by(Dispute.created_at.desc(), Dispute.id.desc())
        .first()
    )


def list_query(
    db: Session,
    *,
    project_id: str | None,
    project_ids: set[str] | None,
    status: str | None,
    target_type: str | None,
    target_id: str | None,
    initiator_id: str | None,
    assigned_to: str | None,
):
    query = db.query(Dispute)
    if project_id is not None:
        query = query.filter(Dispute.project_id == project_id)
    if project_ids is not None:
        query = (
            query.filter(Dispute.project_id.in_(project_ids))
            if project_ids
            else query.filter(false())
        )
    if status is not None:
        query = query.filter(Dispute.status == status)
    if target_type is not None:
        query = query.filter(Dispute.target_type == target_type)
    if target_id is not None:
        query = query.filter(Dispute.target_id == target_id)
    if initiator_id is not None:
        query = query.filter(Dispute.initiator_id == initiator_id)
    if assigned_to is not None:
        query = query.filter(Dispute.assigned_to == assigned_to)
    return query.order_by(Dispute.created_at.desc(), Dispute.id.desc())


def insert_event(
    db: Session,
    *,
    dispute_id: str,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    actor_id: str | None,
    metadata: dict,
) -> DisputeEvent:
    row = DisputeEvent(
        dispute_id=dispute_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        event_metadata=metadata,
    )
    db.add(row)
    db.flush()
    return row


def events_for_dispute(db: Session, dispute_id: str) -> list[DisputeEvent]:
    return (
        db.query(DisputeEvent)
        .filter(DisputeEvent.dispute_id == dispute_id)
        .order_by(DisputeEvent.created_at.asc(), DisputeEvent.id.asc())
        .all()
    )
