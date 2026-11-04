"""BE-015 audit-ledger repository: append, fetch, query, ranges.

Deliberately exposes no mutation or deletion path: existing rows are
never updated or deleted through the application layer.
"""

from sqlalchemy.orm import Session

from backend.db.models import AuditLedgerEvent


def insert_event(db: Session, **fields) -> AuditLedgerEvent:
    row = AuditLedgerEvent(**fields)
    db.add(row)
    db.flush()
    return row


def get_event(db: Session, event_id: str) -> AuditLedgerEvent | None:
    return db.query(AuditLedgerEvent).filter(AuditLedgerEvent.id == event_id).one_or_none()


def latest(db: Session) -> AuditLedgerEvent | None:
    return (
        db.query(AuditLedgerEvent)
        .order_by(AuditLedgerEvent.sequence_number.desc())
        .first()
    )


def range_query(db: Session, from_sequence: int | None, to_sequence: int | None):
    query = db.query(AuditLedgerEvent)
    if from_sequence is not None:
        query = query.filter(AuditLedgerEvent.sequence_number >= from_sequence)
    if to_sequence is not None:
        query = query.filter(AuditLedgerEvent.sequence_number <= to_sequence)
    return query.order_by(AuditLedgerEvent.sequence_number)


def list_query(
    db: Session,
    *,
    event_type: str | None,
    action: str | None,
    actor_id: str | None,
    resource_type: str | None,
    resource_id: str | None,
    project_id: str | None,
    since=None,
    until=None,
):
    query = db.query(AuditLedgerEvent)
    if event_type is not None:
        query = query.filter(AuditLedgerEvent.event_type == event_type)
    if action is not None:
        query = query.filter(AuditLedgerEvent.action == action)
    if actor_id is not None:
        query = query.filter(AuditLedgerEvent.actor_id == actor_id)
    if resource_type is not None:
        query = query.filter(AuditLedgerEvent.resource_type == resource_type)
    if resource_id is not None:
        query = query.filter(AuditLedgerEvent.resource_id == resource_id)
    if project_id is not None:
        query = query.filter(AuditLedgerEvent.project_id == project_id)
    if since is not None:
        query = query.filter(AuditLedgerEvent.created_at >= since)
    if until is not None:
        query = query.filter(AuditLedgerEvent.created_at <= until)
    return query.order_by(AuditLedgerEvent.sequence_number)
