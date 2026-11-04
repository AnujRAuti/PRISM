"""BE-022 public endpoints: read-only access to published information.

§17: public endpoints MUST NOT require internal authentication for genuinely
public content, but they MUST still enforce publication state. Every route
here reads only through the service's published-snapshot path, so a DRAFT,
REJECTED, or UNPUBLISHED publication is simply not found — publication
state, not caller identity, is the gate.

No internal ORM object is ever serialized directly: responses use the
explicit public projection schemas, which carry no storage key, EXIF,
internal UUID, reviewer identity, or internal signal values.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.observability import publication_metrics as metrics
from backend.schemas import publication as publication_schemas
from backend.services import publication as publication_service

router = APIRouter(prefix="/public")

# Public listing is mandatory-paginated (§29): never an unbounded public query.
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


def _not_found(message: str) -> HTTPException:
    metrics.record_public_error("NOT_FOUND")
    return HTTPException(status_code=404, detail=message)


def _public_project_response(snapshot: dict) -> publication_schemas.PublicProjectResponse:
    """Project list/detail projection — content already allowlisted upstream."""
    content = snapshot.get("content") or {}
    return publication_schemas.PublicProjectResponse(
        public_id=snapshot["public_id"],
        name=content.get("name") or "",
        description=content.get("description"),
        status=snapshot.get("status", "PUBLISHED"),
    )


def _provenance(snapshot: dict) -> publication_schemas.PublicProvenance:
    """Build the public-safe provenance block from a published snapshot."""
    provenance = snapshot.get("provenance") or {}
    return publication_schemas.PublicProvenance(
        publication_version=snapshot.get("version_number", 1),
        source_category=provenance.get("source_category"),
        published_at=snapshot.get("published_at"),
        human_approval_status=provenance.get("human_approval_status"),
    )


@router.get(
    "/projects",
    response_model=List[publication_schemas.PublicProjectResponse],
    summary="List published projects",
)
def list_public_projects(
    db: Session = Depends(get_db),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> List[publication_schemas.PublicProjectResponse]:
    """List published projects. Requires no internal authentication."""
    metrics.record_public_request()
    try:
        rows = publication_service.list_public_projects(db, limit=limit, offset=offset)
    except ValueError as error:
        metrics.record_public_error("SERVER_ERROR")
        raise HTTPException(status_code=422, detail=str(error)) from error
    return [_public_project_response(row) for row in rows]


@router.get(
    "/projects/{public_id}",
    response_model=publication_schemas.PublicProjectDetailResponse,
    summary="Get a published project by public ID",
)
def get_public_project(
    public_id: str,
    db: Session = Depends(get_db),
) -> publication_schemas.PublicProjectDetailResponse:
    """Get a published project by public ID."""
    metrics.record_public_request()
    try:
        snapshot = publication_service.get_public_project(db, public_id)
    except LookupError as error:
        raise _not_found(str(error)) from error
    except ValueError as error:
        metrics.record_public_error("SERVER_ERROR")
        raise HTTPException(status_code=422, detail=str(error)) from error
    content = snapshot.get("content") or {}
    return publication_schemas.PublicProjectDetailResponse(
        public_id=snapshot["public_id"],
        name=content.get("name") or "",
        description=content.get("description"),
        status=snapshot.get("status", "PUBLISHED"),
        published_at=snapshot.get("published_at"),
        provenance=_provenance(snapshot),
    )


def _activity_response(snapshot: dict) -> publication_schemas.PublicActivityResponse:
    content = snapshot.get("content") or {}
    return publication_schemas.PublicActivityResponse(
        public_id=snapshot["public_id"],
        verb=content.get("verb") or "",
        occurred_at=content.get("occurred_at"),
    )


def _claim_response(snapshot: dict) -> publication_schemas.PublicClaimResponse:
    content = snapshot.get("content") or {}
    return publication_schemas.PublicClaimResponse(
        public_id=snapshot["public_id"],
        public_project_id=content.get("public_project_id"),
        title=content.get("title") or "",
        description=content.get("description"),
        temporal_start_at=content.get("temporal_start_at"),
        temporal_end_at=content.get("temporal_end_at"),
        status=snapshot.get("status", "PUBLISHED"),
    )


def _evidence_response(snapshot: dict) -> publication_schemas.PublicEvidenceResponse:
    content = snapshot.get("content") or {}
    return publication_schemas.PublicEvidenceResponse(
        public_id=snapshot["public_id"],
        public_project_id=content.get("public_project_id"),
        status=snapshot.get("status", "PUBLISHED"),
        collected_at=content.get("collected_at"),
        media=[
            publication_schemas.PublicMediaResponse(
                public_id=item.get("public_id", ""),
                derivative_type=item.get("derivative_type", "ORIGINAL"),
            )
            for item in (content.get("media") or [])
        ],
    )


@router.get(
    "/projects/{public_id}/activities",
    response_model=List[publication_schemas.PublicActivityResponse],
    summary="List published activities for a project",
)
def list_public_activities(
    public_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> List[publication_schemas.PublicActivityResponse]:
    """List published activities for a project (actor identity never exposed)."""
    metrics.record_public_request()
    try:
        rows = publication_service.list_public_activities(db, public_id, limit=limit, offset=offset)
    except LookupError as error:
        raise _not_found(str(error)) from error
    except ValueError as error:
        metrics.record_public_error("SERVER_ERROR")
        raise HTTPException(status_code=422, detail=str(error)) from error
    return [_activity_response(row) for row in rows]


@router.get(
    "/projects/{public_id}/claims",
    response_model=List[publication_schemas.PublicClaimResponse],
    summary="List published claims for a project",
)
def list_public_claims(
    public_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> List[publication_schemas.PublicClaimResponse]:
    """List published claims. Internal fusion signals are never included."""
    metrics.record_public_request()
    try:
        rows = publication_service.list_public_claims(db, public_id, limit=limit, offset=offset)
    except LookupError as error:
        raise _not_found(str(error)) from error
    except ValueError as error:
        metrics.record_public_error("SERVER_ERROR")
        raise HTTPException(status_code=422, detail=str(error)) from error
    return [_claim_response(row) for row in rows]


@router.get(
    "/projects/{public_id}/evidence",
    response_model=List[publication_schemas.PublicEvidenceResponse],
    summary="List published evidence for a project",
)
def list_public_evidence(
    public_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> List[publication_schemas.PublicEvidenceResponse]:
    """List published evidence. Storage keys are never exposed."""
    metrics.record_public_request()
    try:
        rows = publication_service.list_public_evidence(db, public_id, limit=limit, offset=offset)
    except LookupError as error:
        raise _not_found(str(error)) from error
    except ValueError as error:
        metrics.record_public_error("SERVER_ERROR")
        raise HTTPException(status_code=422, detail=str(error)) from error
    return [_evidence_response(row) for row in rows]


@router.get(
    "/evidence/{public_id}",
    response_model=publication_schemas.PublicEvidenceDetailResponse,
    summary="Get published evidence by public ID",
)
def get_public_evidence(
    public_id: str,
    db: Session = Depends(get_db),
) -> publication_schemas.PublicEvidenceDetailResponse:
    """Get published evidence by public ID."""
    metrics.record_public_request()
    try:
        snapshot = publication_service.get_public_evidence(db, public_id)
    except LookupError as error:
        raise _not_found(str(error)) from error
    except ValueError as error:
        metrics.record_public_error("SERVER_ERROR")
        raise HTTPException(status_code=422, detail=str(error)) from error
    content = snapshot.get("content") or {}
    return publication_schemas.PublicEvidenceDetailResponse(
        public_id=snapshot["public_id"],
        public_project_id=content.get("public_project_id"),
        status=snapshot.get("status", "PUBLISHED"),
        collected_at=content.get("collected_at"),
        media=[
            publication_schemas.PublicMediaResponse(
                public_id=item.get("public_id", ""),
                derivative_type=item.get("derivative_type", "ORIGINAL"),
            )
            for item in (content.get("media") or [])
        ],
        filename=content.get("filename"),
        # §22: only a policy-reduced precision label or coarse area, never a
        # raw private coordinate pair.
        location_area=content.get("location"),
        location_precision=content.get("location_precision", "HIDDEN"),
        provenance=_provenance(snapshot),
    )


@router.get(
    "/publications/{public_id}",
    response_model=publication_schemas.PublicPublicationResponse,
    summary="Get a published publication snapshot by public ID",
)
def get_public_publication(
    public_id: str,
    db: Session = Depends(get_db),
) -> publication_schemas.PublicPublicationResponse:
    """Get the current PUBLISHED snapshot for a public identifier."""
    metrics.record_public_request()
    try:
        snapshot = publication_service.get_public_publication(db, public_id)
    except LookupError as error:
        raise _not_found(str(error)) from error
    except ValueError as error:
        metrics.record_public_error("SERVER_ERROR")
        raise HTTPException(status_code=422, detail=str(error)) from error
    return publication_schemas.PublicPublicationResponse(
        public_id=snapshot["public_id"],
        target_type=snapshot["target_type"],
        version_number=snapshot["version_number"],
        status=snapshot["status"],
        published_at=snapshot.get("published_at"),
        provenance=_provenance(snapshot),
        content=snapshot.get("content") or {},
    )
