"""BE-014 evidence-request endpoints (workflow, never verdicts)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.session import get_db
from backend.schemas.evidence_request import (
    EvidenceRequestCreate,
    EvidenceRequestDeclineRequest,
    EvidenceRequestHistoryResponse,
    EvidenceRequestEventItem,
    EvidenceRequestItemResponse,
    EvidenceRequestLinkResponse,
    EvidenceRequestListResponse,
    EvidenceRequestResponse,
    EvidenceRequestResponseAction,
    RequestPriority,
    RequestStatus,
)
from backend.services import evidence_request as request_service
from backend.security.authentication import get_current_principal
from backend.security.authorization import require, visible_project_ids
from backend.services.authorization import Principal


router = APIRouter(prefix="/evidence-requests")


def _item(item) -> EvidenceRequestItemResponse:
    return EvidenceRequestItemResponse.model_validate(item)


def _response(request, items) -> EvidenceRequestResponse:
    body = EvidenceRequestResponse.model_validate(request)
    body.items = [_item(item) for item in items]
    return body


def _load_items(db: Session, request) -> list:
    return request_service.request_items(db, request.id)


def _event_item(event) -> EvidenceRequestEventItem:
    created = event.created_at
    return EvidenceRequestEventItem(
        id=UUID(event.id),
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        actor_id=UUID(event.actor_id) if event.actor_id else None,
        created_at=created.isoformat() if created is not None else None,
    )


@router.post(
    "",
    response_model=EvidenceRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an evidence request with item slots",
)
def create_request(
    payload: EvidenceRequestCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("evidence_request.create")),
) -> EvidenceRequestResponse:
    try:
        request = request_service.create_request(
            db,
            review_case_id=str(payload.review_case_id),
            recipient_id=str(payload.recipient_id),
            instructions=payload.instructions,
            items=[item.model_dump() for item in payload.items],
            requester_id=str(payload.requester_id) if payload.requester_id else None,
            due_at=payload.due_at,
            priority=payload.priority.value,
            project_id=str(payload.project_id) if payload.project_id else None,
            activity_id=str(payload.activity_id) if payload.activity_id else None,
            claim_id=str(payload.claim_id) if payload.claim_id else None,
            evidence_id=str(payload.evidence_id) if payload.evidence_id else None,
            issue=payload.issue,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _response(request, _load_items(db, request))


@router.get(
    "/{request_id}",
    response_model=EvidenceRequestResponse,
    summary="Retrieve one evidence request with its items",
)
def get_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.read", "evidence_request", "request_id")),
) -> EvidenceRequestResponse:
    try:
        request = request_service.get_request(db, str(request_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _response(request, _load_items(db, request))


@router.get(
    "",
    response_model=EvidenceRequestListResponse,
    summary="List evidence requests with optional filters",
)
def list_requests(
    project_id: UUID | None = None,
    review_case_id: UUID | None = None,
    status: RequestStatus | None = None,
    priority: RequestPriority | None = None,
    requester_id: UUID | None = None,
    recipient_id: UUID | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> EvidenceRequestListResponse:
    from backend.security.authentication import is_development_bypass

    project_ids: set[str] | None = None
    if not is_development_bypass(principal):
        if "evidence_request.read" not in principal.permissions:
            raise HTTPException(status_code=403, detail="Forbidden")
        project_ids = visible_project_ids(db, principal, "evidence_request.read")
        if project_id is not None and (
            project_ids is not None and str(project_id) not in project_ids
        ):
            raise HTTPException(status_code=404, detail="Not found")
    try:
        rows, total = request_service.list_requests(
            db,
            project_id=str(project_id) if project_id else None,
            project_ids=project_ids,
            review_case_id=str(review_case_id) if review_case_id else None,
            status=status.value if status else None,
            priority=priority.value if priority else None,
            requester_id=str(requester_id) if requester_id else None,
            recipient_id=str(recipient_id) if recipient_id else None,
            due_before=due_before,
            due_after=due_after,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    items = []
    for row in rows:
        items.append(_response(row, _load_items(db, row)))
    return EvidenceRequestListResponse(items=items, limit=limit, offset=offset, total=total)


@router.get(
    "/{request_id}/history",
    response_model=EvidenceRequestHistoryResponse,
    summary="Append-only history for a request",
)
def get_history(
    request_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.read", "evidence_request", "request_id")),
):
    try:
        events = request_service.request_history(db, str(request_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return EvidenceRequestHistoryResponse(
        request_id=request_id, items=[_event_item(e) for e in events], total=len(events)
    )


@router.post(
    "/{request_id}/issue",
    response_model=EvidenceRequestResponse,
    summary="Issue a DRAFT request",
)
def issue_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.issue", "evidence_request", "request_id")),
):
    try:
        request = request_service.issue_request(db, str(request_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _response(request, _load_items(db, request))


@router.post(
    "/{request_id}/acknowledge",
    response_model=EvidenceRequestResponse,
    summary="Acknowledge a request (idempotent)",
)
def acknowledge_request(
    request_id: UUID, payload: EvidenceRequestResponseAction | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.respond", "evidence_request", "request_id")),
):
    try:
        request = request_service.acknowledge_request(
            db, str(request_id),
            str(payload.actor_id) if payload and payload.actor_id else None,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _response(request, _load_items(db, request))


@router.post(
    "/{request_id}/evidence/{evidence_id}",
    response_model=EvidenceRequestLinkResponse,
    summary="Link existing evidence to a request (idempotent)",
)
def link_evidence(
    request_id: UUID, evidence_id: UUID, response: Response,
    item_id: UUID | None = None, db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.respond", "evidence_request", "request_id")),
):
    try:
        item, created = request_service.link_evidence(
            db, str(request_id), str(evidence_id), None,
            str(item_id) if item_id else None,
        )
        request = request_service.get_request(db, str(request_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return EvidenceRequestLinkResponse(
        item=_item(item), created=created, request_status=request.status
    )


@router.post(
    "/{request_id}/submissions",
    response_model=EvidenceRequestLinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload new evidence through the standard pipeline and link it",
)
async def submit_evidence(
    request_id: UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.respond", "evidence_request", "request_id")),
):
    declared_type = (file.content_type or "").lower().strip()
    data = await file.read(settings.max_upload_size + 1)
    try:
        evidence, item, created = request_service.submit_evidence(
            db, str(request_id), data, file.filename or "unnamed", declared_type, None,
        )
        request = request_service.get_request(db, str(request_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return EvidenceRequestLinkResponse(
        item=_item(item), created=created, request_status=request.status
    )


@router.post(
    "/{request_id}/items/{item_id}/accept",
    response_model=EvidenceRequestItemResponse,
    summary="Accept received evidence for an item (operational only)",
)
def accept_item(
    request_id: UUID,
    item_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.respond", "evidence_request", "request_id")),
):
    try:
        return _item(request_service.accept_item(db, str(request_id), str(item_id)))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{request_id}/items/{item_id}/reject",
    response_model=EvidenceRequestItemResponse,
    summary="Reject received evidence for an item (evidence stays valid)",
)
def reject_item(
    request_id: UUID,
    item_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.respond", "evidence_request", "request_id")),
):
    try:
        return _item(request_service.reject_item(db, str(request_id), str(item_id)))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{request_id}/decline",
    response_model=EvidenceRequestResponse,
    summary="Decline a request with a required reason",
)
def decline_request(
    request_id: UUID,
    payload: EvidenceRequestDeclineRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.respond", "evidence_request", "request_id")),
):
    try:
        request = request_service.decline_request(db, str(request_id), payload.reason)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _response(request, _load_items(db, request))


@router.post(
    "/{request_id}/cancel",
    response_model=EvidenceRequestResponse,
    summary="Cancel a request",
)
def cancel_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.issue", "evidence_request", "request_id")),
):
    try:
        request = request_service.cancel_request(db, str(request_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _response(request, _load_items(db, request))


@router.post(
    "/{request_id}/expire",
    response_model=EvidenceRequestResponse,
    summary="Expire a request with a past due date (explicit, no scheduler)",
)
def expire_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("evidence_request.issue", "evidence_request", "request_id")),
):
    try:
        request = request_service.expire_request(db, str(request_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _response(request, _load_items(db, request))
