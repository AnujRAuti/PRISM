"""BE-021 dispute endpoints: authorized challenges with human resolution.

Governance responses carry reference metadata only — never evidence content
(§24, §34). Scope is enforced server-side: creation resolves the challenged
target's project, workflow actions resolve the dispute's own project, and
out-of-scope resources are indistinguishable from absent (404).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.dispute import (
    DisputeAssignRequest,
    DisputeCreateRequest,
    DisputeEscalateRequest,
    DisputeHistoryResponse,
    DisputeListResponse,
    DisputeEventItem,
    DisputeRejectRequest,
    DisputeResolveRequest,
    DisputeResponse,
    DisputeStatus,
    DisputeTargetType,
    DisputeWithdrawRequest,
)
from backend.security.authentication import get_current_principal, is_development_bypass
from backend.security.authorization import enforce, require, visible_project_ids
from backend.services import dispute as dispute_service
from backend.services.authorization import (
    Principal,
    governance_target_resource,
    resolve_resource_scope,
)


router = APIRouter(prefix="/disputes")


def _item(dispute) -> DisputeResponse:
    return DisputeResponse.model_validate(dispute)


def _event_item(event) -> DisputeEventItem:
    created = event.created_at
    return DisputeEventItem(
        id=UUID(event.id),
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        actor_id=UUID(event.actor_id) if event.actor_id else None,
        created_at=created.isoformat() if created is not None else None,
    )


def _actor(principal: Principal, request_actor: UUID | None) -> str | None:
    """Explicit actor wins; otherwise the authenticated principal."""
    if request_actor is not None:
        return str(request_actor)
    return principal.principal_id


def _enforce_target_scope(
    db: Session, principal: Principal, request: Request, target_type: str, target_id: UUID
) -> None:
    """Server-side scope check on the challenged target (never trusted)."""
    if is_development_bypass(principal):
        return
    resource_type = governance_target_resource(target_type)
    if resource_type is None:
        raise HTTPException(status_code=422, detail="Unsupported dispute target type")
    resource = resolve_resource_scope(db, resource_type, str(target_id))
    enforce(principal, "dispute.create", resource, request)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DisputeResponse,
    summary="Create a dispute against a governed target (idempotent per active target+initiator)",
)
def create_dispute(
    request: Request,
    payload: DisputeCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("dispute.create")),
) -> DisputeResponse:
    _enforce_target_scope(
        db, principal, request, payload.target_type.value, payload.target_id
    )
    initiator = _actor(principal, payload.initiator_id)
    if initiator is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        dispute, created = dispute_service.create_dispute(
            db,
            target_type=payload.target_type.value,
            target_id=str(payload.target_id),
            initiator_id=initiator,
            reason=payload.reason,
            description=payload.description,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _item(dispute)


@router.get(
    "/{dispute_id}",
    response_model=DisputeResponse,
    summary="Retrieve one dispute",
)
def get_dispute(
    dispute_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("dispute.read", "dispute", "dispute_id")),
) -> DisputeResponse:
    try:
        return _item(dispute_service.get_dispute(db, str(dispute_id)))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "",
    response_model=DisputeListResponse,
    summary="List disputes with optional filters",
)
def list_disputes(
    project_id: UUID | None = None,
    status_filter: DisputeStatus | None = Query(None, alias="status"),
    target_type: DisputeTargetType | None = None,
    target_id: UUID | None = None,
    initiator_id: UUID | None = None,
    assigned_to: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> DisputeListResponse:
    project_ids: set[str] | None = None
    if not is_development_bypass(principal):
        if "dispute.read" not in principal.permissions:
            raise HTTPException(status_code=403, detail="Forbidden")
        project_ids = visible_project_ids(db, principal, "dispute.read")
        if project_id is not None and (
            project_ids is not None and str(project_id) not in project_ids
        ):
            raise HTTPException(status_code=404, detail="Not found")
    try:
        rows, total = dispute_service.list_disputes(
            db,
            project_id=str(project_id) if project_id else None,
            project_ids=project_ids,
            status=status_filter.value if status_filter else None,
            target_type=target_type.value if target_type else None,
            target_id=str(target_id) if target_id else None,
            initiator_id=str(initiator_id) if initiator_id else None,
            assigned_to=str(assigned_to) if assigned_to else None,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return DisputeListResponse(
        items=[_item(row) for row in rows], limit=limit, offset=offset, total=total
    )


@router.get(
    "/{dispute_id}/history",
    response_model=DisputeHistoryResponse,
    summary="Append-only workflow history for a dispute",
)
def get_history(
    dispute_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("dispute.read", "dispute", "dispute_id")),
) -> DisputeHistoryResponse:
    try:
        _, events = dispute_service.get_dispute_history(db, str(dispute_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return DisputeHistoryResponse(
        dispute_id=dispute_id,
        items=[_event_item(e) for e in events],
        total=len(events),
    )


@router.post(
    "/{dispute_id}/start-review",
    response_model=DisputeResponse,
    summary="Move a dispute into review (OPEN/ESCALATED -> UNDER_REVIEW)",
)
def start_review(
    dispute_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("dispute.review", "dispute", "dispute_id")),
) -> DisputeResponse:
    try:
        return _item(
            dispute_service.start_review(
                db, str(dispute_id), actor_id=principal.principal_id
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{dispute_id}/assign",
    response_model=DisputeResponse,
    summary="Assign a reviewer to an active dispute",
)
def assign_dispute(
    dispute_id: UUID,
    request: DisputeAssignRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("dispute.review", "dispute", "dispute_id")),
) -> DisputeResponse:
    try:
        return _item(
            dispute_service.assign_dispute(
                db,
                str(dispute_id),
                assigned_to=str(request.assigned_to),
                actor_id=_actor(principal, request.actor_id),
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{dispute_id}/escalate",
    response_model=DisputeResponse,
    summary="Escalate a dispute for higher review",
)
def escalate_dispute(
    dispute_id: UUID,
    request: DisputeEscalateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("dispute.review", "dispute", "dispute_id")),
) -> DisputeResponse:
    try:
        return _item(
            dispute_service.escalate_dispute(
                db,
                str(dispute_id),
                escalated_to=str(request.escalated_to),
                reason=request.reason,
                actor_id=_actor(principal, request.actor_id),
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{dispute_id}/resolve",
    response_model=DisputeResponse,
    summary="Adjudicate a dispute (human-governed resolution vocabulary)",
)
def resolve_dispute(
    dispute_id: UUID,
    request: DisputeResolveRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("dispute.resolve", "dispute", "dispute_id")),
) -> DisputeResponse:
    resolved_by = _actor(principal, request.resolved_by)
    if resolved_by is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        dispute, invalidation = dispute_service.resolve_dispute(
            db,
            str(dispute_id),
            resolution=request.resolution.value,
            rationale=request.rationale,
            resolved_by=resolved_by,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _item(dispute)


@router.post(
    "/{dispute_id}/reject",
    response_model=DisputeResponse,
    summary="Dismiss a challenge outright (no adjudication recorded)",
)
def reject_dispute(
    dispute_id: UUID,
    request: DisputeRejectRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("dispute.resolve", "dispute", "dispute_id")),
) -> DisputeResponse:
    try:
        return _item(
            dispute_service.reject_dispute(
                db,
                str(dispute_id),
                reason=request.rationale,
                actor_id=_actor(principal, request.actor_id),
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{dispute_id}/withdraw",
    response_model=DisputeResponse,
    summary="Withdraw a dispute (initiator only)",
)
def withdraw_dispute(
    dispute_id: UUID,
    request: DisputeWithdrawRequest | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("dispute.read", "dispute", "dispute_id")),
) -> DisputeResponse:
    # Scope is enforced server-side via require(); initiator-only is enforced
    # in the service (§12: withdrawal is the one initiator-only action).
    actor = _actor(principal, request.actor_id if request else None)
    try:
        return _item(
            dispute_service.withdraw_dispute(db, str(dispute_id), actor_id=actor)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
