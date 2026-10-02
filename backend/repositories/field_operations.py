"""BE-026 field operations repository: persistence and deterministic queries.

No ``commit()`` happens here (repository convention): synchronization policy,
authority re-evaluation, and transaction boundaries live in
``backend.services.field_operations``.
"""

from sqlalchemy import false
from sqlalchemy.orm import Session

from backend.db.models import (
    Activity,
    Claim,
    FieldAssignment,
    FieldCaptureOperation,
    FieldSession,
    Project,
)


# ---------------------------------------------------------------------------
# field_assignments
# ---------------------------------------------------------------------------

def insert_assignment(
    db: Session,
    *,
    user_id: str,
    project_id: str,
    organization_id: str | None,
    organizational_unit_id: str | None,
    claim_id: str | None,
    activity_id: str | None,
    valid_from,
    expires_at,
    instructions: str | None,
    created_by: str | None,
) -> FieldAssignment:
    row = FieldAssignment(
        user_id=user_id,
        project_id=project_id,
        organization_id=organization_id,
        organizational_unit_id=organizational_unit_id,
        claim_id=claim_id,
        activity_id=activity_id,
        status="ACTIVE",
        valid_from=valid_from,
        expires_at=expires_at,
        instructions=instructions,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def get_assignment(db: Session, assignment_id: str) -> FieldAssignment | None:
    return db.query(FieldAssignment).filter(FieldAssignment.id == assignment_id).one_or_none()


def lock_assignment(db: Session, assignment_id: str) -> FieldAssignment | None:
    """SELECT ... FOR UPDATE so concurrent lifecycle transitions serialize."""
    return (
        db.query(FieldAssignment)
        .filter(FieldAssignment.id == assignment_id)
        .with_for_update()
        .one_or_none()
    )


def active_assignment_for(
    db: Session, *, user_id: str, project_id: str, claim_id: str | None
) -> FieldAssignment | None:
    """The partial-unique ACTIVE row for one (officer, project[, claim])."""
    query = db.query(FieldAssignment).filter(
        FieldAssignment.user_id == user_id,
        FieldAssignment.project_id == project_id,
        FieldAssignment.status == "ACTIVE",
    )
    query = (
        query.filter(FieldAssignment.claim_id.is_(None))
        if claim_id is None
        else query.filter(FieldAssignment.claim_id == claim_id)
    )
    return query.one_or_none()


def active_assignments_for_user(
    db: Session, user_id: str
) -> list[FieldAssignment]:
    return (
        db.query(FieldAssignment)
        .filter(FieldAssignment.user_id == user_id, FieldAssignment.status == "ACTIVE")
        .order_by(FieldAssignment.created_at.desc(), FieldAssignment.id.desc())
        .all()
    )


def newer_active_assignment(
    db: Session, assignment: FieldAssignment
) -> FieldAssignment | None:
    """True when current state has moved on past this assignment (§4 of the task)."""
    query = db.query(FieldAssignment).filter(
        FieldAssignment.user_id == assignment.user_id,
        FieldAssignment.project_id == assignment.project_id,
        FieldAssignment.status == "ACTIVE",
    )
    if assignment.claim_id is None:
        query = query.filter(FieldAssignment.claim_id.is_(None))
    else:
        query = query.filter(FieldAssignment.claim_id == assignment.claim_id)
    return (
        query.filter(FieldAssignment.id != assignment.id)
        .order_by(FieldAssignment.created_at.desc(), FieldAssignment.id.desc())
        .first()
    )


def assignment_query(
    db: Session,
    *,
    user_id: str | None,
    project_id: str | None,
    project_ids: set[str] | None,
    status: str | None,
):
    query = db.query(FieldAssignment)
    if user_id is not None:
        query = query.filter(FieldAssignment.user_id == user_id)
    if project_id is not None:
        query = query.filter(FieldAssignment.project_id == project_id)
    if project_ids is not None:
        query = (
            query.filter(FieldAssignment.project_id.in_(project_ids))
            if project_ids
            else query.filter(false())
        )
    if status is not None:
        query = query.filter(FieldAssignment.status == status)
    return query.order_by(FieldAssignment.created_at.desc(), FieldAssignment.id.desc())


def paginate(query, limit: int, offset: int) -> tuple[list, int]:
    """Authorization filter is applied to ``query`` before the count (no leakage)."""
    total = query.count()
    return query.offset(offset).limit(limit).all(), total


# ---------------------------------------------------------------------------
# field_sessions
# ---------------------------------------------------------------------------

def insert_session(
    db: Session,
    *,
    assignment_id: str,
    user_id: str,
    project_id: str,
    organization_id: str | None,
    session_label: str | None,
    client_device_id: str | None,
) -> FieldSession:
    row = FieldSession(
        assignment_id=assignment_id,
        user_id=user_id,
        project_id=project_id,
        organization_id=organization_id,
        status="ACTIVE",
        session_label=session_label,
        client_device_id=client_device_id,
    )
    db.add(row)
    db.flush()
    return row


def get_session(db: Session, session_id: str) -> FieldSession | None:
    return db.query(FieldSession).filter(FieldSession.id == session_id).one_or_none()


def lock_session(db: Session, session_id: str) -> FieldSession | None:
    return (
        db.query(FieldSession)
        .filter(FieldSession.id == session_id)
        .with_for_update()
        .one_or_none()
    )


def open_session_for_device(
    db: Session, *, assignment_id: str, client_device_id: str
) -> FieldSession | None:
    return (
        db.query(FieldSession)
        .filter(
            FieldSession.assignment_id == assignment_id,
            FieldSession.client_device_id == client_device_id,
            FieldSession.status == "ACTIVE",
        )
        .one_or_none()
    )


def open_sessions_for_user(db: Session, user_id: str) -> list[FieldSession]:
    """The caller's own open sessions (one row per assignment/device)."""
    return (
        db.query(FieldSession)
        .filter(FieldSession.user_id == user_id, FieldSession.status == "ACTIVE")
        .order_by(FieldSession.started_at.desc(), FieldSession.id.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# field_capture_operations
# ---------------------------------------------------------------------------

def insert_operation(
    db: Session,
    *,
    user_id: str,
    client_operation_id: str,
    client_capture_id: str | None,
    client_device_id: str | None,
    session_id: str | None,
    assignment_id: str | None,
    project_id: str | None,
    claim_id: str | None,
    request_hash: str,
    payload_sha256: str,
    declared_content_type: str | None,
    filename: str | None,
    file_size: int,
    status: str,
    validation_errors: list | None = None,
    captured_at=None,
    queued_at=None,
    uploaded_at=None,
    received_at=None,
    timestamp_flags: list | None = None,
    latitude=None,
    longitude=None,
    capture_accuracy_m=None,
    altitude_m=None,
    location_source: str | None = None,
    zero_island_confirmed: bool = False,
    conflict_reason: str | None = None,
    conflict_detail: dict | None = None,
) -> FieldCaptureOperation:
    row = FieldCaptureOperation(
        user_id=user_id,
        client_operation_id=client_operation_id,
        client_capture_id=client_capture_id,
        client_device_id=client_device_id,
        session_id=session_id,
        assignment_id=assignment_id,
        project_id=project_id,
        claim_id=claim_id,
        request_hash=request_hash,
        payload_sha256=payload_sha256,
        declared_content_type=declared_content_type,
        filename=filename,
        file_size=file_size,
        status=status,
        validation_errors=validation_errors or [],
        captured_at=captured_at,
        queued_at=queued_at,
        uploaded_at=uploaded_at,
        received_at=received_at,
        timestamp_flags=timestamp_flags or [],
        latitude=latitude,
        longitude=longitude,
        capture_accuracy_m=capture_accuracy_m,
        altitude_m=altitude_m,
        location_source=location_source,
        zero_island_confirmed=zero_island_confirmed,
        conflict_reason=conflict_reason,
        conflict_detail=conflict_detail,
    )
    db.add(row)
    db.flush()
    return row


def get_operation(db: Session, operation_id: str) -> FieldCaptureOperation | None:
    return (
        db.query(FieldCaptureOperation)
        .filter(FieldCaptureOperation.id == operation_id)
        .one_or_none()
    )


def lock_operation(db: Session, operation_id: str) -> FieldCaptureOperation | None:
    return (
        db.query(FieldCaptureOperation)
        .filter(FieldCaptureOperation.id == operation_id)
        .with_for_update()
        .one_or_none()
    )


def get_operation_by_client_id(
    db: Session, *, user_id: str, client_operation_id: str
) -> FieldCaptureOperation | None:
    """The row behind the (officer, client_operation_id) identity, if any."""
    return (
        db.query(FieldCaptureOperation)
        .filter(
            FieldCaptureOperation.user_id == user_id,
            FieldCaptureOperation.client_operation_id == client_operation_id,
        )
        .one_or_none()
    )


def lock_operation_by_client_id(
    db: Session, *, user_id: str, client_operation_id: str
) -> FieldCaptureOperation | None:
    """Lock the row behind an operation identity for the whole replay decision.

    A synchronization that finds an existing identity both reads and annotates
    it (replay counter, adoption of an abandoned reservation). Without the
    row lock, two concurrent retries lose each other's increments and two
    concurrent adopters can both ingest.
    """
    return (
        db.query(FieldCaptureOperation)
        .filter(
            FieldCaptureOperation.user_id == user_id,
            FieldCaptureOperation.client_operation_id == client_operation_id,
        )
        .with_for_update()
        .one_or_none()
    )


def operation_query(
    db: Session,
    *,
    user_id: str | None,
    project_id: str | None,
    project_ids: set[str] | None,
    session_id: str | None,
    status: str | None,
    resolution_status: str | None,
):
    query = db.query(FieldCaptureOperation)
    if user_id is not None:
        query = query.filter(FieldCaptureOperation.user_id == user_id)
    if project_id is not None:
        query = query.filter(FieldCaptureOperation.project_id == project_id)
    if project_ids is not None:
        # project_id is NULL on pre-context failures, so an explicit project
        # list never exposes them to a non-GLOBAL caller.
        query = (
            query.filter(FieldCaptureOperation.project_id.in_(project_ids))
            if project_ids
            else query.filter(false())
        )
    if session_id is not None:
        query = query.filter(FieldCaptureOperation.session_id == session_id)
    if status is not None:
        query = query.filter(FieldCaptureOperation.status == status)
    if resolution_status is not None:
        query = query.filter(FieldCaptureOperation.resolution_status == resolution_status)
    return query.order_by(
        FieldCaptureOperation.created_at.desc(), FieldCaptureOperation.id.desc()
    )


# ---------------------------------------------------------------------------
# read-only context hydration (feed data minimization, Stage B §11.1)
# ---------------------------------------------------------------------------

def projects_by_ids(db: Session, project_ids: list[str]) -> dict[str, Project]:
    ids = sorted({str(value) for value in project_ids if value})
    if not ids:
        return {}
    rows = db.query(Project).filter(Project.id.in_(ids)).all()
    return {str(row.id): row for row in rows}


def claims_by_ids(db: Session, claim_ids: list[str]) -> dict[str, Claim]:
    ids = sorted({str(value) for value in claim_ids if value})
    if not ids:
        return {}
    rows = db.query(Claim).filter(Claim.id.in_(ids)).all()
    return {str(row.id): row for row in rows}


def activities_by_ids(db: Session, activity_ids: list[str]) -> dict[str, Activity]:
    ids = sorted({str(value) for value in activity_ids if value})
    if not ids:
        return {}
    rows = db.query(Activity).filter(Activity.id.in_(ids)).all()
    return {str(row.id): row for row in rows}
