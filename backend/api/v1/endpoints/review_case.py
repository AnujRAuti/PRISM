"""BE-013 review-case endpoints (workflow items, not verdicts)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.review_case import (
    CaseAssignmentRequest,
    CaseDecisionRequest,
    CaseEscalationRequest,
    CaseGenerateRequest,
    CaseGenerationConfigurationCreate,
    CaseGenerationConfigurationItem,
    CaseGenerationResponse,
    CaseOrigin,
    CaseStatus,
    ReviewCaseHistoryResponse,
    ReviewCaseEventItem,
    ReviewCaseListResponse,
    ReviewCaseResponse,
)
from backend.services import review_case as case_service
from backend.security.attribution import derive_actor
from backend.security.authentication import get_current_principal, is_development_bypass
from backend.security.authorization import require, visible_project_ids
from backend.services.authorization import Principal


router = APIRouter(prefix="/review-cases")


def _case_item(case) -> ReviewCaseResponse:
    return ReviewCaseResponse.model_validate(case)


def _event_item(event) -> ReviewCaseEventItem:
    created = event.created_at
    return ReviewCaseEventItem(
        id=UUID(event.id),
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        actor_id=UUID(event.actor_id) if event.actor_id else None,
        created_at=created.isoformat() if created is not None else None,
    )


@router.post(
    "/from-fusion/{fusion_run_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Generate a review case from a fusion run (idempotent per run)",
)
def generate_from_fusion(
    fusion_run_id: UUID,
    response: Response,
    request: CaseGenerateRequest | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("fusion.execute", "fusion_run", "fusion_run_id")),
) -> CaseGenerationResponse:
    try:
        case, gen_run, result, reason = case_service.generate_for_fusion(
            db,
            str(fusion_run_id),
            policy_version=(request.policy_version if request else None),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if result == case_service.RESULT_CREATED:
        response.status_code = status.HTTP_201_CREATED
    else:
        response.status_code = status.HTTP_200_OK
    return CaseGenerationResponse(
        result=result,
        reason=reason,
        case=_case_item(case) if case else None,
        generation_run_id=UUID(gen_run.id) if gen_run else None,
    )


@router.get(
    "/{case_id}",
    response_model=ReviewCaseResponse,
    summary="Retrieve one review case",
)
def get_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("review_case.read", "review_case", "case_id")),
) -> ReviewCaseResponse:
    try:
        return _case_item(case_service.get_case(db, str(case_id)))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "",
    response_model=ReviewCaseListResponse,
    summary="List review cases with optional filters",
)
def list_cases(
    project_id: UUID | None = None,
    status: CaseStatus | None = None,
    priority_band: str | None = None,
    origin: CaseOrigin | None = None,
    assigned_to: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> ReviewCaseListResponse:
    project_ids: set[str] | None = None
    if not is_development_bypass(principal):
        if "review_case.read" not in principal.permissions:
            raise HTTPException(status_code=403, detail="Forbidden")
        project_ids = visible_project_ids(db, principal, "review_case.read")
        if project_id is not None and (
            project_ids is not None and str(project_id) not in project_ids
        ):
            raise HTTPException(status_code=404, detail="Not found")
    try:
        rows, total = case_service.list_cases(
            db,
            project_id=str(project_id) if project_id else None,
            status=status.value if status else None,
            priority_band=priority_band,
            origin=origin.value if origin else None,
            assigned_to=str(assigned_to) if assigned_to else None,
            limit=limit,
            offset=offset,
            project_ids=project_ids,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ReviewCaseListResponse(
        items=[_case_item(row) for row in rows], limit=limit, offset=offset, total=total
    )


@router.get(
    "/{case_id}/history",
    response_model=ReviewCaseHistoryResponse,
    summary="Append-only workflow history for a case",
)
def get_history(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("review_case.read", "review_case", "case_id")),
) -> ReviewCaseHistoryResponse:
    try:
        events = case_service.case_history(db, str(case_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ReviewCaseHistoryResponse(
        case_id=case_id, items=[_event_item(e) for e in events], total=len(events)
    )


@router.post(
    "/{case_id}/assign",
    response_model=ReviewCaseResponse,
    summary="Assign a case (or unassign with null)",
)
def assign_case(
    case_id: UUID,
    request: CaseAssignmentRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("review_case.assign", "review_case", "case_id")),
) -> ReviewCaseResponse:
    try:
        return _case_item(
            case_service.assign_case(
                db,
                str(case_id),
                str(request.assigned_to) if request.assigned_to else None,
                derive_actor(principal, request.actor_id),
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{case_id}/investigate",
    response_model=ReviewCaseResponse,
    summary="Move a case into investigation",
)
def investigate_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("review_case.investigate", "review_case", "case_id")),
) -> ReviewCaseResponse:
    try:
        return _case_item(case_service.start_investigation(
            db, str(case_id), derive_actor(principal)))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{case_id}/decision",
    response_model=ReviewCaseResponse,
    summary="Record a human decision (human-supplied only)",
)
def record_decision(
    case_id: UUID,
    request: CaseDecisionRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("review_case.decide", "review_case", "case_id")),
) -> ReviewCaseResponse:
    try:
        return _case_item(
            case_service.record_decision(
                db,
                str(case_id),
                request.decision.value,
                request.rationale,
                derive_actor(principal, request.decided_by, field="decided_by"),
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{case_id}/escalate",
    response_model=ReviewCaseResponse,
    summary="Escalate a case (history-preserving)",
)
def escalate_case(
    case_id: UUID,
    request: CaseEscalationRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("review_case.escalate", "review_case", "case_id")),
) -> ReviewCaseResponse:
    try:
        return _case_item(
            case_service.escalate_case(
                db,
                str(case_id),
                str(request.escalated_to),
                request.reason,
                derive_actor(principal, request.actor_id),
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{case_id}/resolve",
    response_model=ReviewCaseResponse,
    summary="Resolve a case (requires a recorded human decision)",
)
def resolve_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("review_case.resolve", "review_case", "case_id")),
) -> ReviewCaseResponse:
    try:
        return _case_item(case_service.resolve_case(
            db, str(case_id), derive_actor(principal)))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{case_id}/reopen",
    response_model=ReviewCaseResponse,
    summary="Reopen a resolved case (history preserved)",
)
def reopen_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("review_case.reopen", "review_case", "case_id")),
) -> ReviewCaseResponse:
    try:
        return _case_item(case_service.reopen_case(
            db, str(case_id), derive_actor(principal)))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/configurations",
    response_model=CaseGenerationConfigurationItem,
    summary="Store a new immutable case-generation policy version",
)
def create_configuration(
    request: CaseGenerationConfigurationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("configuration.manage")),
) -> CaseGenerationConfigurationItem:
    try:
        row = case_service.create_policy_configuration(
            db,
            version=request.version,
            name=request.name,
            configuration=request.configuration,
            enabled=request.enabled,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return CaseGenerationConfigurationItem.model_validate(row)
