"""BE-013 review-case repository: persistence and deterministic queries only.

Policy evaluation, lifecycle rules, and decision validation live in
``backend.services.review_case``.
"""

from sqlalchemy import false
from sqlalchemy.orm import Session

from backend.db.models import (
    CaseGenerationConfiguration,
    CaseGenerationRun,
    ReviewCase,
    ReviewCaseEvent,
)


def get_configuration(db: Session, version: str) -> CaseGenerationConfiguration | None:
    return (
        db.query(CaseGenerationConfiguration)
        .filter(CaseGenerationConfiguration.version == version)
        .one_or_none()
    )


def insert_configuration(
    db: Session, *, version: str, name: str, configuration: dict, enabled: bool = True
) -> CaseGenerationConfiguration:
    row = CaseGenerationConfiguration(
        version=version, name=name, enabled=enabled, configuration=configuration
    )
    db.add(row)
    db.flush()
    return row


def insert_generation_run(
    db: Session,
    *,
    fusion_run_id: str,
    configuration_id: str,
    method: str,
    method_version: str,
    input_snapshot: dict,
) -> CaseGenerationRun:
    row = CaseGenerationRun(
        fusion_run_id=fusion_run_id,
        configuration_id=configuration_id,
        method=method,
        method_version=method_version,
        input_snapshot=input_snapshot,
        status="RUNNING",
    )
    db.add(row)
    db.flush()
    return row


def active_system_case_for_run(db: Session, fusion_run_id: str) -> ReviewCase | None:
    return (
        db.query(ReviewCase)
        .filter(
            ReviewCase.fusion_run_id == fusion_run_id,
            ReviewCase.origin == "SYSTEM_SIGNAL",
            ReviewCase.status != "RESOLVED",
        )
        .order_by(ReviewCase.created_at.desc(), ReviewCase.id.desc())
        .first()
    )


def open_cases_for_target(
    db: Session, target_type: str, target_id: str
) -> list[ReviewCase]:
    column = {"CLAIM": ReviewCase.claim_id, "EVIDENCE": ReviewCase.evidence_id}[target_type]
    return (
        db.query(ReviewCase)
        .filter(column == target_id, ReviewCase.status != "RESOLVED")
        .order_by(ReviewCase.created_at.desc(), ReviewCase.id.desc())
        .all()
    )


def insert_case(db: Session, **fields) -> ReviewCase:
    row = ReviewCase(**fields)
    db.add(row)
    db.flush()
    return row


def get_case(db: Session, case_id: str) -> ReviewCase | None:
    return db.query(ReviewCase).filter(ReviewCase.id == case_id).one_or_none()


def insert_event(
    db: Session,
    *,
    case_id: str,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    actor_id: str | None,
    metadata: dict,
) -> ReviewCaseEvent:
    row = ReviewCaseEvent(
        case_id=case_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        event_metadata=metadata,
    )
    db.add(row)
    db.flush()
    return row


def events_for_case(db: Session, case_id: str) -> list[ReviewCaseEvent]:
    return (
        db.query(ReviewCaseEvent)
        .filter(ReviewCaseEvent.case_id == case_id)
        .order_by(ReviewCaseEvent.created_at, ReviewCaseEvent.id)
        .all()
    )


def list_query(
    db: Session,
    *,
    project_id: str | None,
    project_ids: set[str] | None,
    status: str | None,
    priority_band: str | None,
    origin: str | None,
    assigned_to: str | None,
):
    query = db.query(ReviewCase)
    if project_id is not None:
        query = query.filter(ReviewCase.project_id == project_id)
    if project_ids is not None:
        query = query.filter(ReviewCase.project_id.in_(project_ids)) if project_ids else query.filter(false())
    if status is not None:
        query = query.filter(ReviewCase.status == status)
    if priority_band is not None:
        query = query.filter(ReviewCase.priority_band == priority_band)
    if origin is not None:
        query = query.filter(ReviewCase.origin == origin)
    if assigned_to is not None:
        query = query.filter(ReviewCase.assigned_to == assigned_to)
    return query.order_by(ReviewCase.created_at.desc(), ReviewCase.id.desc())
