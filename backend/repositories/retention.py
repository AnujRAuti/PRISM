"""BE-017 retention repository: persistence and indexed lookups only.

Policy semantics, evaluation, holds matching, and execution live in
``backend.services.retention``.
"""

from sqlalchemy.orm import Session

from backend.db.models import (
    RetentionHold,
    RetentionOperation,
    RetentionPolicy,
    RetentionPolicyVersion,
    RetentionState,
)


def insert_policy(db: Session, **fields) -> RetentionPolicy:
    row = RetentionPolicy(**fields)
    db.add(row)
    db.flush()
    return row


def get_policy(db: Session, policy_id: str) -> RetentionPolicy | None:
    return db.query(RetentionPolicy).filter(RetentionPolicy.id == policy_id).one_or_none()


def insert_version(
    db: Session, *, policy_id: str, version: int, rules: dict,
    status: str = "DRAFT", effective_from=None, effective_until=None,
    created_by: str | None = None,
) -> RetentionPolicyVersion:
    row = RetentionPolicyVersion(
        policy_id=policy_id, version=version, rules=rules, status=status,
        effective_from=effective_from, effective_until=effective_until,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def versions_for_policy(db: Session, policy_id: str) -> list[RetentionPolicyVersion]:
    return (
        db.query(RetentionPolicyVersion)
        .filter(RetentionPolicyVersion.policy_id == policy_id)
        .order_by(RetentionPolicyVersion.version)
        .all()
    )


def active_version_candidates(
    db: Session, resource_type: str, now
) -> list[tuple[RetentionPolicy, RetentionPolicyVersion]]:
    """ACTIVE versions in their effective window for a resource type."""
    rows = (
        db.query(RetentionPolicy, RetentionPolicyVersion)
        .join(RetentionPolicyVersion,
              RetentionPolicyVersion.policy_id == RetentionPolicy.id)
        .filter(RetentionPolicy.resource_type == resource_type,
                RetentionPolicyVersion.status == "ACTIVE")
        .all()
    )
    applicable = []
    for policy, version in rows:
        if version.effective_from is not None and version.effective_from > now:
            continue
        if version.effective_until is not None and version.effective_until <= now:
            continue
        applicable.append((policy, version))
    return applicable


def get_state(db: Session, resource_type: str, resource_id: str):
    return (
        db.query(RetentionState)
        .filter(RetentionState.resource_type == resource_type,
                RetentionState.resource_id == resource_id)
        .one_or_none()
    )


def upsert_state(db: Session, **fields):
    row = get_state(db, fields["resource_type"], fields["resource_id"])
    if row is None:
        row = RetentionState(**fields)
        db.add(row)
    else:
        for name, value in fields.items():
            if name not in ("resource_type", "resource_id"):
                setattr(row, name, value)
    db.flush()
    return row


def states_expiring_before(db: Session, moment, limit: int = 200):
    """Indexed candidate selection for sweep runs (never a full scan)."""
    return (
        db.query(RetentionState)
        .filter(RetentionState.expiry_timestamp.is_not(None),
                RetentionState.expiry_timestamp <= moment,
                RetentionState.state.in_(("ACTIVE", "ELIGIBLE_FOR_ARCHIVE",
                                          "ELIGIBLE_FOR_DELETION")))
        .order_by(RetentionState.expiry_timestamp, RetentionState.id)
        .limit(limit)
        .all()
    )


def insert_hold(db: Session, **fields) -> RetentionHold:
    row = RetentionHold(**fields)
    db.add(row)
    db.flush()
    return row


def get_hold(db: Session, hold_id: str) -> RetentionHold | None:
    return db.query(RetentionHold).filter(RetentionHold.id == hold_id).one_or_none()


def active_holds(db: Session) -> list[RetentionHold]:
    return db.query(RetentionHold).filter(RetentionHold.status == "ACTIVE").all()


def list_holds_query(db: Session, *, status: str | None, project_id: str | None):
    query = db.query(RetentionHold)
    if status is not None:
        query = query.filter(RetentionHold.status == status)
    if project_id is not None:
        query = query.filter(RetentionHold.project_id == project_id)
    return query.order_by(RetentionHold.created_at.desc(), RetentionHold.id.desc())


def insert_operation(db: Session, **fields) -> RetentionOperation:
    row = RetentionOperation(**fields)
    db.add(row)
    db.flush()
    return row


def completed_delete_for(db: Session, resource_type: str, resource_id: str):
    return (
        db.query(RetentionOperation)
        .filter(RetentionOperation.resource_type == resource_type,
                RetentionOperation.resource_id == resource_id,
                RetentionOperation.operation == "DELETE",
                RetentionOperation.status == "COMPLETED")
        .order_by(RetentionOperation.completed_at.desc(),
                  RetentionOperation.id.desc())
        .first()
    )


def list_operations_query(
    db: Session, *, resource_type: str | None, resource_id: str | None,
    operation: str | None, status: str | None,
):
    query = db.query(RetentionOperation)
    if resource_type is not None:
        query = query.filter(RetentionOperation.resource_type == resource_type)
    if resource_id is not None:
        query = query.filter(RetentionOperation.resource_id == resource_id)
    if operation is not None:
        query = query.filter(RetentionOperation.operation == operation)
    if status is not None:
        query = query.filter(RetentionOperation.status == status)
    return query.order_by(RetentionOperation.created_at.desc(),
                          RetentionOperation.id.desc())
