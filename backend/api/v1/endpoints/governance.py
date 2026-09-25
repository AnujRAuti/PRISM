"""BE-021 governance endpoints: dependency inspection, invalidation, reprocessing.

The dependency engine only marks and records — it never computes new
intelligence, never deletes anything, and never touches evidence bytes.
Scope is resolved server-side from the path's governed target; responses
carry reference metadata only (§24, §34).
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.governance import (
    DependencyGraphResponse,
    GovernanceTargetType,
    InvalidationRequest,
    InvalidationResponse,
    ReprocessRequest,
    ReprocessResponse,
)
from backend.security.authentication import get_current_principal, is_development_bypass
from backend.security.authorization import enforce, require
from backend.services import governance as governance_service
from backend.services.authorization import (
    Principal,
    governance_target_resource,
    resolve_resource_scope,
)


router = APIRouter(prefix="/governance")


def _require_target_scope(action: str):
    """Dependency enforcing ``action`` against the path's governed target.

    Reads ``target_type``/``target_id`` from the path and resolves the
    target's scope server-side (never trusted from the client): missing
    permission -> 403, out-of-scope target -> 404 (indistinguishable from
    absent), unresolvable target type -> 422.
    """

    def dependency(
        request: Request,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if is_development_bypass(principal):
            return principal
        target_type = request.path_params.get("target_type")
        target_id = request.path_params.get("target_id")
        resource_type = governance_target_resource(str(target_type))
        if resource_type is None or target_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported governance target type",
            )
        resource = resolve_resource_scope(db, resource_type, str(target_id))
        return enforce(principal, action, resource, request)

    return dependency


def _actor(principal: Principal, request_actor: UUID | None) -> str | None:
    if request_actor is not None:
        return str(request_actor)
    return principal.principal_id


def _invalidation_item(invalidation) -> InvalidationResponse:
    """Project an invalidation row, normalizing ORM timestamps to ISO strings.

    ``InvalidationResponse.created_at`` is declared ``str`` because that is the
    serialized wire contract (the same convention as the dispute, correction
    and retention responses; see the retention service's ``_iso`` helper).
    Pydantic will not coerce a ``datetime`` into ``str`` under
    ``from_attributes``, so the projection boundary normalizes it here.
    """
    return InvalidationResponse(
        id=UUID(invalidation.id),
        target_type=invalidation.target_type,
        target_id=UUID(invalidation.target_id),
        project_id=UUID(invalidation.project_id) if invalidation.project_id else None,
        cause=invalidation.cause,
        dispute_id=UUID(invalidation.dispute_id) if invalidation.dispute_id else None,
        correction_id=UUID(invalidation.correction_id) if invalidation.correction_id else None,
        reason=invalidation.reason,
        invalidated_by=UUID(invalidation.invalidated_by),
        affected_analysis=invalidation.affected_analysis,
        affected_fusion=invalidation.affected_fusion,
        affected_explanations=invalidation.affected_explanations,
        affected_relationships=invalidation.affected_relationships,
        affected_assessments=invalidation.affected_assessments,
        created_at=(
            invalidation.created_at.isoformat()
            if isinstance(invalidation.created_at, datetime)
            else invalidation.created_at
        ),
    )


@router.get(
    "/{target_type}/{target_id}/dependencies",
    response_model=DependencyGraphResponse,
    summary="Inspect the bounded downstream dependency graph of a governed target",
)
def get_dependencies(
    target_type: GovernanceTargetType,
    target_id: UUID,
    max_depth: int = Query(
        governance_service.MAX_TRAVERSAL_DEPTH,
        ge=1,
        le=governance_service.MAX_TRAVERSAL_DEPTH,
        description="Traversal depth bound (hard-capped server-side)",
    ),
    max_nodes: int = Query(
        governance_service.MAX_TRAVERSAL_NODES,
        ge=1,
        le=governance_service.MAX_TRAVERSAL_NODES,
        description="Traversal node bound (hard-capped server-side)",
    ),
    db: Session = Depends(get_db),
    principal: Principal = Depends(_require_target_scope("intelligence.invalidate")),
) -> DependencyGraphResponse:
    try:
        result = governance_service.discover_dependencies(
            db,
            target_type.value,
            str(target_id),
            max_depth=max_depth,
            max_nodes=max_nodes,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return DependencyGraphResponse(**result)


@router.post(
    "/{target_type}/{target_id}/invalidate",
    status_code=status.HTTP_201_CREATED,
    response_model=InvalidationResponse,
    summary="Invalidate a governed target's downstream derived intelligence (DIRECT cause)",
)
def invalidate(
    target_type: GovernanceTargetType,
    target_id: UUID,
    request: InvalidationRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(_require_target_scope("intelligence.invalidate")),
) -> InvalidationResponse:
    actor = _actor(principal, request.invalidated_by)
    if actor is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        invalidation, _reprocessing = governance_service.invalidate_target(
            db,
            target_type=target_type.value,
            target_id=str(target_id),
            cause="DIRECT",
            reason=request.reason,
            invalidated_by=actor,
            reprocess=request.reprocess,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _invalidation_item(invalidation)


@router.get(
    "/invalidations/{invalidation_id}",
    response_model=InvalidationResponse,
    summary="Retrieve one intelligence invalidation record",
)
def get_invalidation(
    invalidation_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require("intelligence.invalidate", "intelligence_invalidation", "invalidation_id")
    ),
) -> InvalidationResponse:
    try:
        return _invalidation_item(
            governance_service.get_invalidation(db, str(invalidation_id))
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/{target_type}/{target_id}/reprocess",
    response_model=ReprocessResponse,
    summary="Request reprocessing of one evidence item through the existing pipeline (idempotent per PENDING)",
)
def reprocess(
    target_type: GovernanceTargetType,
    target_id: UUID,
    request: ReprocessRequest,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(_require_target_scope("intelligence.reprocess")),
) -> ReprocessResponse:
    # Reprocessing is per evidence item (§17): the existing BE-005 analysis
    # pipeline is the only reprocessing mechanism.
    if target_type is not GovernanceTargetType.EVIDENCE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only evidence targets can be reprocessed",
        )
    requester = _actor(principal, request.requested_by)
    if requester is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        reprocessing, result = governance_service.request_reprocessing(
            db,
            evidence_id=str(target_id),
            requested_by=requester,
            reason=request.reason,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    response.status_code = (
        status.HTTP_201_CREATED
        if result == "REPROCESSING_REQUESTED"
        else status.HTTP_200_OK
    )
    return ReprocessResponse(
        result=result,
        reason=request.reason,
        reprocessing_request_id=reprocessing.id,
        evidence_id=reprocessing.evidence_id,
        status=reprocessing.status,
        analysis_job_id=reprocessing.analysis_job_id,
    )
