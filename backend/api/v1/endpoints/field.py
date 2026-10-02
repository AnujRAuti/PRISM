"""BE-026 field operations endpoints.

Eleven operations: assignment administration, the assigned-work feed, session
lifecycle, one-capture offline synchronization, owner-side operation recovery,
manager-side outcome visibility, and terminal conflict annotation.

Every guard is the existing BE-016 plane. Synchronization deliberately accepts
no ``project_id``, ``organization_id`` or role claim in any form field: the
unknown-field check below is what turns BE-019's client-supplied-scope pattern
(SR-12) into a hard 422 here instead of a silently ignored escalation attempt.
"""

from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.session import get_db
from backend.schemas import field_operations as field_schemas
from backend.security.authorization import require
from backend.security.authentication import is_development_bypass
from backend.services import field_operations as field_service
from backend.services.authorization import Principal

router = APIRouter(prefix="/field")

#: The complete synchronization form vocabulary. Anything else is refused.
SYNC_FORM_FIELDS = frozenset(
    {
        "file",
        "client_operation_id",
        "client_capture_id",
        "client_device_id",
        "session_id",
        "captured_at",
        "queued_at",
        "uploaded_at",
        "latitude",
        "longitude",
        "capture_accuracy_m",
        "altitude_m",
        "location_source",
        "zero_island_confirmed",
    }
)

_ERROR_RESPONSES = {
    400: "Empty capture payload. Raised by the existing ingestion validator; "
         "BE-026 reuses it rather than adding a second one.",
    401: "Authentication required. Field surfaces bind rows to an identified "
         "officer, so even the development bypass cannot stand in for one.",
    403: "Permission not held (field.sync or field_assignment.manage).",
    404: "Target absent or outside the caller's scope; out-of-scope is reported "
         "exactly like missing so these routes cannot enumerate other officers' "
         "work.",
    409: "Conflict: a duplicate assignment, a closed context, or an explicit "
         "synchronization conflict carrying sync_status \"conflict\".",
    413: "Capture exceeds the configured upload limit (existing validator).",
    415: "Unsupported or mismatched image content type (existing validator).",
    422: "Request validation or capture metadata rejected (naive timestamp, "
         "half a GPS fix, unconfirmed 0,0, unknown field).",
    503: "Synchronization temporarily unavailable (dependency outage or an "
         "execution already in flight for this operation identity).",
}


def _error_docs(*codes: int) -> dict[int, dict[str, str]]:
    return {code: {"description": _ERROR_RESPONSES[code]} for code in codes}


def _manager_actor(principal: Principal) -> Principal | None:
    """Administrative actor; ``None`` only under the explicit development bypass."""
    return None if is_development_bypass(principal) else principal


def _field_error(error: field_service.FieldOperationError) -> HTTPException:
    """Map a service failure, keeping the sync vocabulary where it applies."""
    if error.sync_status:
        return HTTPException(
            status_code=error.status_code,
            detail={
                "sync_status": error.sync_status,
                "message": error.detail,
                "validation_errors": error.validation_errors,
            },
        )
    return HTTPException(status_code=error.status_code, detail=error.detail)


def _form_text(form, key: str) -> str | None:
    value = form.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _call(db: Session, action, *args, **kwargs):
    """Run a service call and translate its deterministic failure."""
    try:
        return action(db, *args, **kwargs)
    except field_service.FieldOperationError as error:
        raise _field_error(error) from error


# ---------------------------------------------------------------------------
# assignment administration
# ---------------------------------------------------------------------------

@router.post(
    "/assignments",
    response_model=field_schemas.FieldAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a field assignment (requires field_assignment.manage)",
    description="Operational work only: an assignment grants no authority. The "
    "capturing officer still needs a scoped evidence.create grant covering the "
    "project, re-evaluated at every synchronization. Organization and unit are "
    "derived from the project, never accepted from the caller.",
    responses=_error_docs(401, 403, 404, 409, 422),
)
def create_assignment(
    payload: field_schemas.FieldAssignmentCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field_assignment.manage")),
) -> field_schemas.FieldAssignmentResponse:
    row = _call(
        db,
        field_service.create_assignment,
        user_id=str(payload.user_id),
        project_id=str(payload.project_id),
        claim_id=str(payload.claim_id) if payload.claim_id else None,
        activity_id=str(payload.activity_id) if payload.activity_id else None,
        valid_from=payload.valid_from,
        expires_at=payload.expires_at,
        instructions=payload.instructions,
        actor=_manager_actor(principal),
        project_permission="field_assignment.manage",
    )
    return field_schemas.FieldAssignmentResponse.model_validate(row)


@router.get(
    "/assignments",
    response_model=field_schemas.FieldAssignmentListResponse,
    summary="List field assignments (requires field_assignment.manage)",
    responses=_error_docs(401, 403, 404, 422),
)
def list_assignments(
    user_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    assignment_status: Optional[field_schemas.FieldAssignmentStatus] = Query(
        default=None, alias="status"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field_assignment.manage")),
) -> field_schemas.FieldAssignmentListResponse:
    rows, total = _call(
        db,
        field_service.list_assignments,
        actor=_manager_actor(principal),
        project_permission="field_assignment.manage",
        user_id=str(user_id) if user_id else None,
        project_id=str(project_id) if project_id else None,
        status=assignment_status.value if assignment_status else None,
        limit=limit,
        offset=offset,
    )
    return field_schemas.FieldAssignmentListResponse(
        items=[field_schemas.FieldAssignmentResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/assignments/{assignment_id}",
    response_model=field_schemas.FieldAssignmentResponse,
    summary="Read one field assignment (requires field_assignment.manage)",
    description="Administrative read. Officers see their own assignments through "
    "the assigned-work feed, which is scoped to them and carries no "
    "administrative fields.",
    responses=_error_docs(401, 403, 404, 422),
)
def get_assignment(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field_assignment.manage")),
) -> field_schemas.FieldAssignmentResponse:
    row = _call(
        db,
        field_service.get_assignment,
        assignment_id=str(assignment_id),
        actor=_manager_actor(principal),
        project_permission="field_assignment.manage",
    )
    return field_schemas.FieldAssignmentResponse.model_validate(row)


@router.patch(
    "/assignments/{assignment_id}/status",
    response_model=field_schemas.FieldAssignmentResponse,
    summary="Release or revoke a field assignment (requires field_assignment.manage)",
    description="Never deletes. A closed assignment stays as the historical "
    "record, and captures queued against it afterwards resolve to an explicit "
    "synchronization conflict rather than being silently accepted.",
    responses=_error_docs(401, 403, 404, 409, 422),
)
def change_assignment_status(
    assignment_id: UUID,
    payload: field_schemas.FieldAssignmentStatusUpdateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field_assignment.manage")),
) -> field_schemas.FieldAssignmentResponse:
    row = _call(
        db,
        field_service.change_assignment_status,
        assignment_id=str(assignment_id),
        new_status=payload.status.value,
        reason=payload.reason,
        actor=_manager_actor(principal),
        project_permission="field_assignment.manage",
    )
    return field_schemas.FieldAssignmentResponse.model_validate(row)


# ---------------------------------------------------------------------------
# officer surfaces
# ---------------------------------------------------------------------------

@router.get(
    "/work",
    response_model=field_schemas.FieldWorkListResponse,
    summary="Assigned-work feed for the calling officer (requires field.sync)",
    description="Authorization-filtered before counting, and limited to this "
    "officer's own active assignments plus the context each one names. Exposes "
    "nothing about other projects, claims, activities, evidence, or reviews.",
    responses=_error_docs(401, 403, 422),
)
def get_work_feed(
    assignment_id: Optional[UUID] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field.sync")),
) -> field_schemas.FieldWorkListResponse:
    items, total = _call(
        db,
        field_service.work_feed,
        principal=principal,
        assignment_id=str(assignment_id) if assignment_id else None,
        limit=limit,
        offset=offset,
    )
    return field_schemas.FieldWorkListResponse(
        items=[field_schemas.FieldWorkItem(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/sessions",
    response_model=field_schemas.FieldSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a field session against one of the caller's assignments (requires field.sync)",
    description="The session is minted server-side after current authority is "
    "re-checked, so a stored assignment snapshot confers nothing on its own.",
    responses=_error_docs(401, 403, 404, 409, 422),
)
def open_session(
    payload: field_schemas.FieldSessionOpenRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field.sync")),
) -> field_schemas.FieldSessionResponse:
    row = _call(
        db,
        field_service.open_session,
        assignment_id=str(payload.assignment_id),
        session_label=payload.session_label,
        client_device_id=payload.client_device_id,
        principal=principal,
    )
    return field_schemas.FieldSessionResponse.model_validate(row)


@router.post(
    "/sessions/{session_id}/close",
    response_model=field_schemas.FieldSessionResponse,
    summary="Close the caller's own field session (requires field.sync)",
    responses=_error_docs(401, 403, 404, 409, 422),
)
def close_session(
    session_id: UUID,
    payload: field_schemas.FieldSessionCloseRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field.sync")),
) -> field_schemas.FieldSessionResponse:
    row = _call(
        db,
        field_service.close_session,
        session_id=str(session_id),
        reason=payload.reason,
        principal=principal,
    )
    return field_schemas.FieldSessionResponse.model_validate(row)


@router.post(
    "/sync",
    response_model=field_schemas.FieldSyncResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Synchronize one offline capture (requires field.sync)",
    description="Multipart, one capture per request. Reuses the existing "
    "ingestion validator, quarantine storage, hashing and audit ledger; the "
    "operation identity is (officer, client_operation_id), so a retry answers "
    "with the stored outcome instead of a second Evidence row. Authority, "
    "assignment state and session state are re-evaluated on every call. The "
    "project, claim and location association are resolved from server rows.",
    responses=_error_docs(400, 401, 403, 404, 409, 413, 415, 422, 503),
)
async def synchronize_capture(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field.sync")),
) -> field_schemas.FieldSyncResponse:
    form = await request.form()
    unknown = sorted(set(str(key) for key in form) - SYNC_FORM_FIELDS)
    if unknown:
        # An unexpected scope-bearing field is a refusal, never an ignore.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "sync_status": field_schemas.FieldSyncStatus.VALIDATION_FAILED.value,
                "message": f"Unsupported synchronization fields: {', '.join(unknown)}",
                "validation_errors": [f"UNEXPECTED_FIELD_{name.upper()}" for name in unknown],
            },
        )
    client_operation_id = _form_text(form, "client_operation_id")
    if not client_operation_id or len(client_operation_id) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "sync_status": field_schemas.FieldSyncStatus.VALIDATION_FAILED.value,
                "message": "client_operation_id is required and must be at least 8 characters",
                "validation_errors": ["CLIENT_OPERATION_ID_TOO_SHORT"],
            },
        )
    # Bounded read, exactly like POST /evidence: one byte past the limit
    # proves oversize without loading an arbitrary upload into memory.
    data = await file.read(settings.max_upload_size + 1)
    declared_type = (file.content_type or "").lower().strip() or None
    try:
        req = field_service.build_sync_request(
            principal=principal,
            data=data,
            filename=file.filename,
            declared_content_type=declared_type,
            client_operation_id=client_operation_id,
            client_capture_id=_form_text(form, "client_capture_id"),
            client_device_id=_form_text(form, "client_device_id"),
            session_id=_form_text(form, "session_id"),
            captured_at=_form_text(form, "captured_at"),
            queued_at=_form_text(form, "queued_at"),
            uploaded_at=_form_text(form, "uploaded_at"),
            latitude=_form_text(form, "latitude"),
            longitude=_form_text(form, "longitude"),
            capture_accuracy_m=_form_text(form, "capture_accuracy_m"),
            altitude_m=_form_text(form, "altitude_m"),
            location_source=_form_text(form, "location_source"),
            zero_island_confirmed=_form_text(form, "zero_island_confirmed"),
        )
        payload, http_status = field_service.sync_capture(db, req, principal)
    except field_service.FieldOperationError as error:
        raise _field_error(error) from error
    response.status_code = http_status
    return field_schemas.FieldSyncResponse(**payload)


@router.get(
    "/captures/{client_operation_id}",
    response_model=field_schemas.FieldCaptureOperationResponse,
    summary="Recover the stored outcome for one of the caller's captures (requires field.sync)",
    description="Lets a client that lost a response resolve the operation "
    "identity it already used. Owner-only; another officer's identifier is "
    "indistinguishable from a missing one.",
    responses=_error_docs(401, 403, 404, 422),
)
def get_capture(
    client_operation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field.sync")),
) -> field_schemas.FieldCaptureOperationResponse:
    row = _call(
        db,
        field_service.get_capture_by_client_id,
        principal=principal,
        client_operation_id=client_operation_id,
    )
    return field_schemas.FieldCaptureOperationResponse.model_validate(row)


# ---------------------------------------------------------------------------
# manager surfaces
# ---------------------------------------------------------------------------

@router.get(
    "/operations",
    response_model=field_schemas.FieldOperationListResponse,
    summary="List synchronization outcomes and open conflicts (requires field_assignment.manage)",
    responses=_error_docs(401, 403, 404, 422),
)
def list_operations(
    user_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    session_id: Optional[UUID] = None,
    operation_status: Optional[field_schemas.FieldOperationStatus] = Query(
        default=None, alias="status"
    ),
    resolution_status: Optional[field_schemas.FieldResolutionStatus] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field_assignment.manage")),
) -> field_schemas.FieldOperationListResponse:
    rows, total = _call(
        db,
        field_service.list_operations,
        actor=_manager_actor(principal),
        project_permission="field_assignment.manage",
        user_id=str(user_id) if user_id else None,
        project_id=str(project_id) if project_id else None,
        session_id=str(session_id) if session_id else None,
        status=operation_status.value if operation_status else None,
        resolution_status=(
            resolution_status.value if resolution_status else None
        ),
        limit=limit,
        offset=offset,
    )
    return field_schemas.FieldOperationListResponse(
        items=[
            field_schemas.FieldCaptureOperationResponse.model_validate(row) for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/operations/{operation_id}/resolve",
    response_model=field_schemas.FieldCaptureOperationResponse,
    summary="Resolve a synchronization conflict (requires field_assignment.manage)",
    description="A human annotation on a terminal record. Resolution ingests "
    "nothing, changes no Evidence, and never clears the conflict fields; the "
    "capture must be re-submitted under a new client_operation_id.",
    responses=_error_docs(401, 403, 404, 409, 422),
)
def resolve_conflict(
    operation_id: UUID,
    payload: field_schemas.FieldConflictResolveRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("field_assignment.manage")),
) -> field_schemas.FieldCaptureOperationResponse:
    row = _call(
        db,
        field_service.resolve_conflict,
        operation_id=str(operation_id),
        outcome=payload.outcome.value,
        note=payload.note,
        actor=_manager_actor(principal),
        project_permission="field_assignment.manage",
    )
    return field_schemas.FieldCaptureOperationResponse.model_validate(row)
