"""BE-015 audit ledger endpoints (read-only; no mutation path exists)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.repositories import audit_ledger as audit_repo
from backend.schemas.audit_ledger import (
    AuditAnchoredVerificationResponse,
    AuditEventListResponse,
    AuditEventResponse,
    AuditVerificationResponse,
)
from backend.services import audit_ledger as audit_service
from backend.services.audit_integrity_baseline import BASELINES
from backend.security.authorization import require_global
from backend.services.authorization import Principal


router = APIRouter(prefix="/audit")


@router.get(
    "/events/{event_id}",
    response_model=AuditEventResponse,
    summary="Retrieve one audit event by ID",
)
def get_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_global("audit.read")),
) -> AuditEventResponse:
    row = audit_repo.get_event(db, str(event_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return AuditEventResponse.model_validate(row)


@router.get(
    "/events",
    response_model=AuditEventListResponse,
    summary="List audit events with optional filters",
)
def list_events(
    event_type: str | None = None,
    action: str | None = None,
    actor_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    project_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_global("audit.read")),
) -> AuditEventListResponse:
    try:
        if since is not None and since.tzinfo is None:
            raise ValueError("since must be timezone-aware")
        if until is not None and until.tzinfo is None:
            raise ValueError("until must be timezone-aware")
        query = audit_repo.list_query(
            db,
            event_type=event_type,
            action=action,
            actor_id=str(actor_id) if actor_id else None,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            project_id=str(project_id) if project_id else None,
            since=since,
            until=until,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    rows = query.offset(offset).limit(limit).all()
    return AuditEventListResponse(
        items=[AuditEventResponse.model_validate(row) for row in rows],
        limit=limit,
        offset=offset,
        total=query.count(),
    )


@router.get(
    "/verify",
    response_model=AuditVerificationResponse,
    summary="Verify hash chain continuity over a (possibly bounded) range",
)
def verify_ledger(
    from_sequence: int | None = Query(default=None, ge=1),
    to_sequence: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_global("audit.read")),
) -> AuditVerificationResponse:
    try:
        result = audit_service.verify_chain(db, from_sequence, to_sequence)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return AuditVerificationResponse(**result)


@router.get(
    "/verify/anchored",
    response_model=AuditAnchoredVerificationResponse,
    summary="Anchored whole-chain verification with checkpoint and gap classification",
)
def verify_ledger_anchored(
    baseline: str | None = Query(
        default=None,
        description=(
            "Name of a reviewed historical-gap baseline to classify findings "
            "against. Omitting it uses the safe default (nothing is blessed as "
            "historical); an unknown name is rejected rather than silently "
            "ignored."
        ),
    ),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_global("audit.read")),
) -> AuditAnchoredVerificationResponse:
    if baseline is not None and baseline not in BASELINES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown baseline {baseline!r}; registered baselines: "
                   f"{sorted(BASELINES)}",
        )
    result = audit_service.verify_chain_classified(db, baseline)
    return AuditAnchoredVerificationResponse(**result)
