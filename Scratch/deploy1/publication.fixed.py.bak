"""BE-022 publication endpoints: governed publication requests and policies."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas import publication as publication_schemas
from backend.security.authentication import get_current_principal, is_development_bypass
from backend.security.authorization import require, require_global, visible_project_ids
from backend.services import publication as publication_service
from backend.services.authorization import Principal

router = APIRouter(prefix="/publications")


def _get_principal_or_raise(principal: Principal) -> str:
    """Resolve the actor identity that will be persisted in UUID-backed columns.

    BE-022 records the acting principal in ``Publication.requested_by``,
    ``approver_id``, ``publisher_id``, ``PublicationEvent.actor_id`` and the
    BE-015 audit ledger — all of which are UUID columns referencing
    ``users.id``.

    A ``Principal.principal_id`` is an *authorization* identity, not
    necessarily a persisted user id: an anonymous principal has ``None`` and
    ``system_principal()`` uses the sentinel ``"system"``. Neither is a UUID,
    so neither may be written to those columns.

    The previous implementation invented the literal string ``"dev-user"``
    during development bypass, which reached PostgreSQL as
    ``invalid input syntax for type uuid: "dev-user"``. This now follows the
    BE-021 dispute pattern: return the real principal identity, or require one.
    Authorization is unchanged — ``require(...)`` has already run.
    """
    if is_development_bypass(principal) and not principal.principal_id:
        raise HTTPException(
            status_code=401,
            detail=(
                "Authentication required: development bypass does not identify a "
                "user, so no actor can be attributed to this action"
            ),
        )
    if not principal.principal_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal.principal_id


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=publication_schemas.PublicationResponse,
    summary="Create a publication request",
)
def create_publication(
    payload: publication_schemas.PublicationCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("publication.create")),
) -> publication_schemas.PublicationResponse:
    """Create a new publication request."""
    principal_id = _get_principal_or_raise(principal)
    try:
        publication, created = publication_service.create_publication(
            db,
            {
                "policy_id": str(payload.policy_id),
                "target_type": payload.target_type.value,
                "target_id": str(payload.target_id),
                "reason": payload.reason,
            },
            principal_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )
    return publication_schemas.PublicationResponse.model_validate(publication)


# Literal single-segment paths must be declared before ``/{publication_id}``:
# routing matches in declaration order, so a path registered after it is
# unreachable (the shadowed ``GET /policies`` returned 422 for publication_id
# = "policies").
@router.get(
    "/policies",
    response_model=publication_schemas.PublicationPolicyListResponse,
    summary="List publication policies",
)
def list_publication_policies(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_global("publication.read")),
) -> publication_schemas.PublicationPolicyListResponse:
    """List publication policies (GLOBAL-scope holders only)."""
    try:
        rows, total = publication_service.list_publication_policies(db)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return publication_schemas.PublicationPolicyListResponse(
        items=[publication_schemas.PublicationPolicyResponse.model_validate(row) for row in rows],
        limit=len(rows),
        offset=0,
        total=total,
    )


@router.get(
    "/{publication_id}",
    response_model=publication_schemas.PublicationResponse,
    summary="Get a publication request by ID",
)
def get_publication(
    publication_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("publication.read", "publication", "publication_id")),
) -> publication_schemas.PublicationResponse:
    """Get a publication request by ID."""
    try:
        return publication_schemas.PublicationResponse.model_validate(
            publication_service.get_publication(db, publication_id)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "",
    response_model=publication_schemas.PublicationListResponse,
    summary="List publication requests with optional filters",
)
def list_publications(
    project_id: Optional[str] = None,
    target_type: Optional[publication_schemas.PublicationTargetType] = None,
    target_id: Optional[str] = None,
    status: Optional[publication_schemas.PublicationStatus] = None,
    requested_by: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> publication_schemas.PublicationListResponse:
    """List publication requests with optional filters."""
    project_ids: Optional[List[str]] = None
    if not is_development_bypass(principal):
        if "publication.read" not in principal.permissions:
            raise HTTPException(status_code=403, detail="Forbidden")
        project_ids = visible_project_ids(db, principal, "publication.read")
        if project_id is not None and (
            project_ids is not None and project_id not in project_ids
        ):
            raise HTTPException(status_code=404, detail="Not found")
    try:
        rows, total = publication_service.list_publications(
            db,
            project_id=project_id,
            project_ids=project_ids,
            target_type=target_type.value if target_type else None,
            target_id=target_id,
            status=status.value if status else None,
            requested_by=requested_by,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return publication_schemas.PublicationListResponse(
        items=[publication_schemas.PublicationResponse.model_validate(row) for row in rows],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.post(
    "/{publication_id}/submit-review",
    response_model=publication_schemas.PublicationResponse,
    summary="Submit a publication request for review",
)
def submit_review(
    publication_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("publication.create", "publication", "publication_id")),
) -> publication_schemas.PublicationResponse:
    """Submit a publication request for review.

    The DRAFT -> PENDING_REVIEW handover is the requester submitting their own
    work, so it is gated on ``publication.create`` (the permission that admits
    an actor to raise a request at all) and the service additionally requires
    the actor to be the requester. ``publication.review`` is deliberately not
    required here: it belongs to whoever later adjudicates the request, and
    submission confers no publication authority.
    """
    principal_id = _get_principal_or_raise(principal)
    try:
        return publication_schemas.PublicationResponse.model_validate(
            publication_service.submit_review(db, publication_id, principal_id)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{publication_id}/approve",
    response_model=publication_schemas.PublicationResponse,
    summary="Approve a publication request",
)
def approve_publication(
    publication_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("publication.approve", "publication", "publication_id")),
) -> publication_schemas.PublicationResponse:
    """Approve a publication request."""
    principal_id = _get_principal_or_raise(principal)
    try:
        return publication_schemas.PublicationResponse.model_validate(
            publication_service.approve_publication(db, publication_id, principal_id)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{publication_id}/reject",
    response_model=publication_schemas.PublicationResponse,
    summary="Reject a publication request",
)
def reject_publication(
    publication_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("publication.approve", "publication", "publication_id")),
) -> publication_schemas.PublicationResponse:
    """Reject a publication request."""
    principal_id = _get_principal_or_raise(principal)
    try:
        return publication_schemas.PublicationResponse.model_validate(
            publication_service.reject_publication(db, publication_id, principal_id)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{publication_id}/publish",
    response_model=publication_schemas.PublicationResponse,
    summary="Publish an approved publication request",
)
def publish_publication(
    publication_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("publication.publish", "publication", "publication_id")),
) -> publication_schemas.PublicationResponse:
    """Publish an approved publication request."""
    principal_id = _get_principal_or_raise(principal)
    try:
        return publication_schemas.PublicationResponse.model_validate(
            publication_service.publish_publication(db, publication_id, principal_id)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{publication_id}/unpublish",
    response_model=publication_schemas.PublicationResponse,
    summary="Unpublish a published publication request",
)
def unpublish_publication(
    publication_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("publication.unpublish", "publication", "publication_id")),
) -> publication_schemas.PublicationResponse:
    """Unpublish a published publication request."""
    principal_id = _get_principal_or_raise(principal)
    try:
        return publication_schemas.PublicationResponse.model_validate(
            publication_service.unpublish_publication(db, publication_id, principal_id)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/{publication_id}/eligibility",
    response_model=publication_schemas.EligibilityResponse,
    summary="Check publication eligibility for a request",
)
def check_eligibility(
    publication_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("publication.read", "publication", "publication_id")),
) -> publication_schemas.EligibilityResponse:
    """Check publication eligibility for a request."""
    try:
        eligibility = publication_service.check_eligibility(db, publication_id)
        return publication_schemas.EligibilityResponse(**eligibility)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


# Publication Policy endpoints
@router.post(
    "/policies",
    status_code=status.HTTP_201_CREATED,
    response_model=publication_schemas.PublicationPolicyResponse,
    summary="Create a publication policy",
)
def create_publication_policy(
    payload: publication_schemas.PublicationPolicyCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_global("publication.policy.manage")),
) -> publication_schemas.PublicationPolicyResponse:
    """Create a new publication policy."""
    # PublicationPolicyVersion.created_by is a NULLABLE UUID column, so an
    # unattributable (development-bypass/anonymous) actor is recorded as NULL
    # rather than rejected or fabricated. An authenticated principal whose id
    # is not a UUID is still rejected downstream as a 422.
    principal_id = principal.principal_id
    try:
        policy, created = publication_service.create_publication_policy(
            db,
            {
                "name": payload.name,
                "description": payload.description,
                "version": payload.version,
                "allowed_target_types": payload.allowed_target_types,
                "public_fields": payload.public_fields,
                "prohibited_fields": payload.prohibited_fields,
                "allow_media_exposure": payload.allow_media_exposure,
                "allow_derived_intelligence": payload.allow_derived_intelligence,
                "allow_review_outcomes": payload.allow_review_outcomes,
                "min_authorization_level": payload.min_authorization_level,
                "required_approvals": payload.required_approvals,
                "require_separation_of_duties": payload.require_separation_of_duties,
                "location_precision": payload.location_precision,
                "retention_publication_duration_days": payload.retention_publication_duration_days,
                "geographic_restrictions": payload.geographic_restrictions,
                "privacy_restrictions": payload.privacy_restrictions,
                "redaction_level": payload.redaction_level,
            },
            principal_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )
    return publication_schemas.PublicationPolicyResponse.model_validate(policy)


@router.get(
    "/policies/{policy_id}",
    response_model=publication_schemas.PublicationPolicyResponse,
    summary="Get a publication policy by ID",
)
def get_publication_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("publication.read", "publication_policy", "policy_id")),
) -> publication_schemas.PublicationPolicyResponse:
    """Get a publication policy by ID."""
    try:
        return publication_schemas.PublicationPolicyResponse.model_validate(
            publication_service.get_publication_policy(db, policy_id)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


# NOTE: PublicationVersion endpoints are intentionally omitted as versions
# are created implicitly through the publication workflow and are immutable.