"""BE-021 correction endpoints: governed context changes on evidence.

Corrections never rewrite evidence bytes or checksums (§8); approval and
application are distinct human steps (§10). The requester is role-separated
from the resolver/applicant (§12), and scope is enforced server-side against
the targeted evidence (creation) or the request's project (workflow).
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.correction import (
    CorrectionApplyRequest,
    CorrectionCancelRequest,
    CorrectionCreateRequest,
    CorrectionDecisionRequest,
    CorrectionEventItem,
    CorrectionHistoryResponse,
    CorrectionListResponse,
    CorrectionResponse,
    CorrectionStatus,
)
from backend.security.attribution import derive_actor
from backend.security.authentication import get_current_principal, is_development_bypass
from backend.security.authorization import enforce, require, visible_project_ids
from backend.services import correction as correction_service
from backend.services.authorization import Principal, resolve_resource_scope


router = APIRouter(prefix="/corrections")


def _iso(value):
    """ORM timestamps are datetimes; the response contract serializes ISO strings.

    Mirrors the retention service's ``_iso`` helper: a ``str`` timestamp field
    in a PoA response schema is an ISO-8601 string on the wire, and Pydantic
    will not coerce a datetime into one. The projection boundary normalizes it
    here rather than widening the schema to ``datetime``.
    """
    return value.isoformat() if isinstance(value, datetime) else value


def _item(correction) -> CorrectionResponse:
    return CorrectionResponse(
        id=UUID(correction.id),
        target_type=correction.target_type,
        target_id=UUID(correction.target_id),
        project_id=UUID(correction.project_id) if correction.project_id else None,
        category=correction.category,
        requested_change=correction.requested_change or {},
        reason=correction.reason,
        requester_id=UUID(correction.requester_id),
        status=correction.status,
        resolver_id=UUID(correction.resolver_id) if correction.resolver_id else None,
        resolution_rationale=correction.resolution_rationale,
        resolved_at=_iso(correction.resolved_at),
        applied_by=UUID(correction.applied_by) if correction.applied_by else None,
        applied_at=_iso(correction.applied_at),
        applied_change=correction.applied_change,
        created_at=_iso(correction.created_at),
        updated_at=_iso(correction.updated_at),
    )


def _event_item(event) -> CorrectionEventItem:
    return CorrectionEventItem(
        id=UUID(event.id),
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        actor_id=UUID(event.actor_id) if event.actor_id else None,
        created_at=event.created_at.isoformat() if event.created_at is not None else None,
    )


def _actor(principal: Principal, request_actor: UUID | None, *,
           field: str = "actor_id") -> str | None:
    """The authenticated principal is the actor; the body may only restate it."""
    return derive_actor(principal, request_actor, field=field)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CorrectionResponse,
    summary="Request a correction to mutable evidence context (idempotent per active target+category+requester)",
)
def create_correction(
    request: Request,
    payload: CorrectionCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("correction.create")),
) -> CorrectionResponse:
    if not is_development_bypass(principal):
        resource = resolve_resource_scope(db, "evidence", str(payload.target_id))
        enforce(principal, "correction.create", resource, request)
    requester = _actor(principal, payload.requester_id, field="requester_id")
    if requester is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        correction, created = correction_service.create_correction(
            db,
            target_type=payload.target_type.value,
            target_id=str(payload.target_id),
            category=payload.category.value,
            requested_change=payload.requested_change,
            reason=payload.reason,
            requester_id=requester,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _item(correction)


@router.get(
    "/{correction_id}",
    response_model=CorrectionResponse,
    summary="Retrieve one correction request",
)
def get_correction(
    correction_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("correction.read", "correction_request", "correction_id")
    ),
) -> CorrectionResponse:
    try:
        return _item(correction_service.get_correction(db, str(correction_id)))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "",
    response_model=CorrectionListResponse,
    summary="List correction requests with optional filters",
)
def list_corrections(
    project_id: UUID | None = None,
    status_filter: CorrectionStatus | None = Query(None, alias="status"),
    category: str | None = None,
    target_id: UUID | None = None,
    requester_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> CorrectionListResponse:
    project_ids: set[str] | None = None
    if not is_development_bypass(principal):
        if "correction.read" not in principal.permissions:
            raise HTTPException(status_code=403, detail="Forbidden")
        project_ids = visible_project_ids(db, principal, "correction.read")
        if project_id is not None and (
            project_ids is not None and str(project_id) not in project_ids
        ):
            raise HTTPException(status_code=404, detail="Not found")
    try:
        rows, total = correction_service.list_corrections(
            db,
            project_id=str(project_id) if project_id else None,
            project_ids=project_ids,
            status=status_filter.value if status_filter else None,
            category=category,
            target_id=str(target_id) if target_id else None,
            requester_id=str(requester_id) if requester_id else None,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return CorrectionListResponse(
        items=[_item(row) for row in rows], limit=limit, offset=offset, total=total
    )


@router.get(
    "/{correction_id}/history",
    response_model=CorrectionHistoryResponse,
    summary="Append-only workflow history for a correction request",
)
def get_history(
    correction_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("correction.read", "correction_request", "correction_id")
    ),
) -> CorrectionHistoryResponse:
    try:
        _, events = correction_service.get_correction_history(db, str(correction_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return CorrectionHistoryResponse(
        correction_id=correction_id,
        items=[_event_item(e) for e in events],
        total=len(events),
    )


@router.post(
    "/{correction_id}/start-review",
    response_model=CorrectionResponse,
    summary="Move a correction into review (REQUESTED -> UNDER_REVIEW)",
)
def start_review(
    correction_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("correction.approve", "correction_request", "correction_id")
    ),
) -> CorrectionResponse:
    try:
        return _item(
            correction_service.start_review(
                db, str(correction_id), actor_id=principal.principal_id
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{correction_id}/approve",
    response_model=CorrectionResponse,
    summary="Approve a correction request (role-separated from the requester)",
)
def approve_correction(
    correction_id: UUID,
    request: CorrectionDecisionRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("correction.approve", "correction_request", "correction_id")
    ),
) -> CorrectionResponse:
    resolver = _actor(principal, request.resolver_id, field="resolver_id")
    try:
        return _item(
            correction_service.approve_correction(
                db, str(correction_id), rationale=request.rationale, resolver_id=resolver
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{correction_id}/reject",
    response_model=CorrectionResponse,
    summary="Reject a correction request (role-separated from the requester)",
)
def reject_correction(
    correction_id: UUID,
    request: CorrectionDecisionRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("correction.approve", "correction_request", "correction_id")
    ),
) -> CorrectionResponse:
    resolver = _actor(principal, request.resolver_id, field="resolver_id")
    try:
        return _item(
            correction_service.reject_correction(
                db, str(correction_id), rationale=request.rationale, resolver_id=resolver
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{correction_id}/apply",
    response_model=CorrectionResponse,
    summary="Apply an approved correction (distinct from approval; immutable evidence untouched)",
)
def apply_correction(
    correction_id: UUID,
    request: CorrectionApplyRequest | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("correction.apply", "correction_request", "correction_id")
    ),
) -> CorrectionResponse:
    applicant = _actor(principal, request.applied_by if request else None, field="applied_by")
    try:
        correction, _invalidation, _reprocessing = correction_service.apply_correction(
            db, str(correction_id), applied_by=applicant
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _item(correction)


@router.post(
    "/{correction_id}/cancel",
    response_model=CorrectionResponse,
    summary="Cancel a correction request (requester only)",
)
def cancel_correction(
    correction_id: UUID,
    request: CorrectionCancelRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("correction.read", "correction_request", "correction_id")
    ),
) -> CorrectionResponse:
    # Scope is enforced server-side via require(); requester-only is enforced
    # in the service (§12: cancellation is the requester's own action).
    actor = _actor(principal, request.actor_id)
    try:
        return _item(
            correction_service.cancel_correction(
                db, str(correction_id), reason=request.reason, actor_id=actor
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
