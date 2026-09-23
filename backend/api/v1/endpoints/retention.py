"""BE-017 retention governance endpoints (policy-driven, fail-closed)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.repositories import retention as retention_repo
from backend.schemas.retention import (
    EvaluateRequest,
    HoldCreate,
    HoldListResponse,
    HoldRelease,
    HoldResponse,
    HoldScope,
    OperationListResponse,
    OperationResponse,
    OperationResultResponse,
    OperationType,
    PolicyCreate,
    PolicyResponse,
    PolicyVersionCreate,
    PolicyVersionResponse,
    ResourceRetentionResponse,
    RetentionEvaluationResponse,
    RetentionResourceType,
    RetentionStateValue,
)
from backend.security.authentication import get_current_principal
from backend.security.authorization import enforce, require, require_global
from backend.services import retention as retention_service
from backend.services.authorization import Principal, Resource


router = APIRouter(prefix="/retention")


def _actor(principal: Principal) -> str | None:
    if principal.principal_type in ("USER", "API_CLIENT") and principal.principal_id:
        try:
            return str(UUID(principal.principal_id))
        except ValueError:
            return None
    return None


def _enforce_scope(
    db: Session,
    request: Request,
    principal: Principal,
    action: str,
    scope: dict,
) -> None:
    """Enforce an action against a server-resolved scope (never body-trusted)."""
    from backend.security.authentication import is_development_bypass

    if is_development_bypass(principal):
        return
    enforce(
        principal,
        action,
        Resource(
            "retention",
            project_id=scope.get("project_id"),
            organization_id=scope.get("organization_id"),
            organizational_unit_id=scope.get("organizational_unit_id"),
        ),
        request,
    )


def _enforce_target_scope(
    db: Session, request: Request, principal: Principal,
    resource_type: str, resource_id: str, action: str,
) -> None:
    """Enforce an action against a retention target's server-resolved scope."""
    from backend.security.authentication import is_development_bypass

    if is_development_bypass(principal):
        return
    try:
        scope = retention_service.resource_scope(db, resource_type, resource_id)
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    _enforce_scope(db, request, principal, action, scope)


def _enforce_policy_scope(
    db: Session, request: Request, principal: Principal, policy_id: str, action: str
) -> None:
    """Enforce an action against a policy's own scope (404 when absent)."""
    from backend.repositories import retention as retention_repo

    policy = retention_repo.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    _enforce_scope(
        db, request, principal, action,
        {"project_id": str(policy.project_id) if policy.project_id else None,
         "organization_id": str(policy.organization_id) if policy.organization_id else None,
         "organizational_unit_id": str(policy.organizational_unit_id)
         if policy.organizational_unit_id else None},
    )


@router.post(
    "/policies",
    response_model=PolicyResponse,
    summary="Create a retention policy identity (requires retention.manage_policy)",
)
def create_policy(
    payload: PolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> PolicyResponse:
    _enforce_scope(
        db, request, principal, "retention.manage_policy",
        {"project_id": str(payload.project_id) if payload.project_id else None,
         "organization_id": str(payload.organization_id) if payload.organization_id else None,
         "organizational_unit_id": str(payload.organizational_unit_id)
         if payload.organizational_unit_id else None},
    )
    try:
        row = retention_service.create_policy(
            db, name=payload.name, description=payload.description,
            resource_type=payload.resource_type.value, scope_type=payload.scope_type.value,
            organization_id=str(payload.organization_id) if payload.organization_id else None,
            organizational_unit_id=str(payload.organizational_unit_id)
            if payload.organizational_unit_id else None,
            project_id=str(payload.project_id) if payload.project_id else None,
            created_by=_actor(principal),
        )
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return PolicyResponse.model_validate(row)


@router.get(
    "/policies/{policy_id}",
    response_model=PolicyResponse,
    summary="Retrieve a retention policy (requires retention.read)",
)
def get_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("retention.read")),
) -> PolicyResponse:
    row = retention_repo.get_policy(db, str(policy_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    return PolicyResponse.model_validate(row)


@router.get(
    "/policies",
    response_model=list[PolicyResponse],
    summary="List retention policies (requires retention.read)",
)
def list_policies(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("retention.read")),
) -> list[PolicyResponse]:
    from backend.db.models import RetentionPolicy

    rows = db.query(RetentionPolicy).order_by(
        RetentionPolicy.created_at, RetentionPolicy.id).all()
    return [PolicyResponse.model_validate(row) for row in rows]


@router.post(
    "/policies/{policy_id}/versions",
    response_model=PolicyVersionResponse,
    summary="Append an immutable policy version (requires retention.manage_policy)",
)
def create_policy_version(
    policy_id: UUID,
    payload: PolicyVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> PolicyVersionResponse:
    _enforce_policy_scope(db, request, principal, str(policy_id), "retention.manage_policy")
    try:
        row = retention_service.create_policy_version(
            db, policy_id=str(policy_id),
            rules={"retention_days": payload.rules.retention_days,
                   "archive_after_days": payload.rules.archive_after_days,
                   "anchor": payload.rules.anchor.value,
                   "allow_derived_cleanup": payload.rules.allow_derived_cleanup},
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
            created_by=_actor(principal),
        )
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return PolicyVersionResponse.model_validate(row)


@router.get(
    "/policies/{policy_id}/history",
    response_model=list[PolicyVersionResponse],
    summary="Version history for a policy (requires retention.read)",
)
def policy_history(
    policy_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("retention.read")),
) -> list[PolicyVersionResponse]:
    if retention_repo.get_policy(db, str(policy_id)) is None:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    rows = retention_repo.versions_for_policy(db, str(policy_id))
    return [PolicyVersionResponse.model_validate(row) for row in rows]


@router.post(
    "/policies/versions/{version_id}/activate",
    response_model=PolicyVersionResponse,
    summary="Activate a version, superseding siblings (requires retention.manage_policy)",
)
def activate_policy_version(
    version_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> PolicyVersionResponse:
    from backend.db.models import RetentionPolicyVersion

    row = db.query(RetentionPolicyVersion).filter(
        RetentionPolicyVersion.id == str(version_id)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Policy version not found")
    _enforce_policy_scope(db, request, principal, str(row.policy_id),
                          "retention.manage_policy")
    try:
        row = retention_service.activate_policy_version(
            db, str(version_id), actor_id=_actor(principal))
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return PolicyVersionResponse.model_validate(row)


@router.post(
    "/evaluate",
    response_model=RetentionEvaluationResponse,
    summary="Dry-run retention evaluation (read-only, requires retention.read)",
)
def evaluate_resource(
    payload: EvaluateRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> RetentionEvaluationResponse:
    _enforce_target_scope(
        db, request, principal, payload.resource_type.value, str(payload.resource_id),
        "retention.read",
    )
    try:
        result = retention_service.evaluate(
            db, payload.resource_type.value, str(payload.resource_id))
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return RetentionEvaluationResponse(
        eligible=result["eligible"], archive_eligible=result["archive_eligible"],
        deletion_eligible=result["deletion_eligible"],
        state=RetentionStateValue(result["state"]), anchor=result["anchor"],
        anchor_timestamp=result["anchor_timestamp"],
        expiry_timestamp=result["expiry_timestamp"], policy_id=result["policy_id"],
        policy_version=result["policy_version"],
        blocking_reasons=result["blocking_reasons"], details=result["details"],
        evaluated_at=result["evaluated_at"],
    )


@router.get(
    "/resources/{resource_type}/{resource_id}",
    response_model=ResourceRetentionResponse,
    summary="Retention state and evaluation for a resource (requires retention.read)",
)
def get_resource_retention(
    resource_type: RetentionResourceType,
    resource_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> ResourceRetentionResponse:
    _enforce_target_scope(
        db, request, principal, resource_type.value, str(resource_id), "retention.read",
    )
    try:
        result = retention_service.evaluate(
            db, resource_type.value, str(resource_id))
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    stored = retention_repo.get_state(db, resource_type.value, str(resource_id))
    return ResourceRetentionResponse(
        resource_type=resource_type, resource_id=resource_id,
        persisted_state=stored.state if stored else None,
        evaluation=RetentionEvaluationResponse(
            eligible=result["eligible"], archive_eligible=result["archive_eligible"],
            deletion_eligible=result["deletion_eligible"],
            state=RetentionStateValue(result["state"]), anchor=result["anchor"],
            anchor_timestamp=result["anchor_timestamp"],
            expiry_timestamp=result["expiry_timestamp"], policy_id=result["policy_id"],
            policy_version=result["policy_version"],
            blocking_reasons=result["blocking_reasons"], details=result["details"],
            evaluated_at=result["evaluated_at"]),
    )


@router.get(
    "/holds",
    response_model=HoldListResponse,
    summary="List holds (requires retention.read)",
)
def list_holds(
    status: str | None = None,
    project_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("retention.read")),
) -> HoldListResponse:
    try:
        rows, total = retention_service.list_holds(
            db, status=status,
            project_id=str(project_id) if project_id else None,
            limit=limit, offset=offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    from backend.schemas.retention import HoldResponse

    return HoldListResponse(
        items=[HoldResponse.model_validate(row) for row in rows],
        limit=limit, offset=offset, total=total)


def _enforce_hold_scope(
    db: Session, request: Request, principal: Principal, payload: HoldCreate,
) -> None:
    """Enforce hold creation against the hold's own scope (server-resolved)."""
    scope: dict[str, str | None] = {
        "project_id": str(payload.project_id) if payload.project_id else None,
        "organization_id": str(payload.organization_id) if payload.organization_id else None,
        "organizational_unit_id": None,
    }
    if scope["project_id"] is None:
        if payload.scope == HoldScope.PROJECT and payload.project_id:
            scope["project_id"] = str(payload.project_id)
        elif payload.scope == HoldScope.RESOURCE and payload.resource_id:
            try:
                resolved = retention_service.resource_scope(
                    db, payload.resource_type.value if payload.resource_type else "EVIDENCE",
                    str(payload.resource_id))
                scope.update({key: resolved.get(key) for key in scope})
            except (ValueError, LookupError):
                pass
        elif payload.scope == HoldScope.CASE and payload.case_id:
            from backend.db.models import ReviewCase

            case = db.query(ReviewCase).filter(
                ReviewCase.id == str(payload.case_id)).one_or_none()
            if case is not None and case.project_id:
                scope["project_id"] = str(case.project_id)
        elif payload.scope == HoldScope.CLAIM and payload.claim_id:
            from backend.db.models import Claim

            claim = db.query(Claim).filter(
                Claim.id == str(payload.claim_id)).one_or_none()
            if claim is not None:
                scope["project_id"] = str(claim.project_id)
        elif payload.scope == HoldScope.ORGANIZATION and payload.organization_id:
            scope["organization_id"] = str(payload.organization_id)
    _enforce_scope(db, request, principal, "retention.manage_hold", scope)


@router.post(
    "/holds",
    response_model=HoldResponse,
    summary="Create a hold (requires retention.manage_hold)",
)
def create_hold(
    payload: HoldCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> HoldResponse:
    _enforce_hold_scope(db, request, principal, payload)
    try:
        row = retention_service.create_hold(
            db, scope=payload.scope.value, reason=payload.reason,
            resource_type=payload.resource_type.value if payload.resource_type else None,
            resource_id=str(payload.resource_id) if payload.resource_id else None,
            project_id=str(payload.project_id) if payload.project_id else None,
            claim_id=str(payload.claim_id) if payload.claim_id else None,
            case_id=str(payload.case_id) if payload.case_id else None,
            organization_id=str(payload.organization_id) if payload.organization_id else None,
            authority=payload.authority, expires_at=payload.expires_at,
            created_by=_actor(principal),
        )
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return HoldResponse.model_validate(row)


@router.get(
    "/holds/{hold_id}",
    response_model=HoldResponse,
    summary="Retrieve a hold (requires retention.read)",
)
def get_hold(
    hold_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("retention.read")),
) -> HoldResponse:
    row = retention_repo.get_hold(db, str(hold_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Retention hold not found")
    return HoldResponse.model_validate(row)


def _enforce_hold_row(
    db: Session, request: Request, principal: Principal, hold_id: str,
) -> None:
    """Enforce manage_hold against an existing hold's own scope."""
    row = retention_repo.get_hold(db, hold_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Retention hold not found")
    _enforce_scope(
        db, request, principal, "retention.manage_hold",
        {"project_id": str(row.project_id) if row.project_id else None,
         "organization_id": str(row.organization_id) if row.organization_id else None,
         "organizational_unit_id": None},
    )


@router.post(
    "/holds/{hold_id}/release",
    response_model=HoldResponse,
    summary="Release a hold with history preserved (requires retention.manage_hold)",
)
def release_hold(
    hold_id: UUID,
    payload: HoldRelease,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> HoldResponse:
    _enforce_hold_row(db, request, principal, str(hold_id))
    try:
        row = retention_service.release_hold(
            db, str(hold_id), payload.release_reason,
            released_by=str(payload.released_by) if payload.released_by else _actor(principal))
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return HoldResponse.model_validate(row)


@router.post(
    "/holds/{hold_id}/cancel",
    response_model=HoldResponse,
    summary="Cancel a hold (terminal, record retained; requires retention.manage_hold)",
)
def cancel_hold(
    hold_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> HoldResponse:
    _enforce_hold_row(db, request, principal, str(hold_id))
    try:
        row = retention_service.cancel_hold(db, str(hold_id), actor_id=_actor(principal))
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return HoldResponse.model_validate(row)


def _enforce_evidence_scope(
    db: Session, request: Request, principal: Principal,
    evidence_id: str, action: str,
) -> None:
    """Enforce a retention action against an evidence item's own project."""
    from backend.db.models import Evidence

    row = db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    _enforce_scope(
        db, request, principal, action,
        {"project_id": str(row.project_id) if row.project_id else None,
         "organization_id": None, "organizational_unit_id": None},
    )


@router.post(
    "/archive/{resource_type}/{resource_id}",
    response_model=OperationResultResponse,
    summary="Archive a resource (requires retention.archive)",
)
def archive_resource(
    resource_type: RetentionResourceType,
    resource_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> OperationResultResponse:
    if resource_type != RetentionResourceType.EVIDENCE:
        raise HTTPException(
            status_code=422,
            detail=f"Archive execution is not supported for {resource_type.value}",
        )
    _enforce_evidence_scope(db, request, principal, str(resource_id), "retention.archive")
    try:
        result = retention_service.archive_evidence(
            db, str(resource_id), _actor(principal))
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return OperationResultResponse(
        result=result["result"], operation_id=result.get("operation_id"),
        storage_key=result.get("storage_key"), evaluation=result.get("evaluation", {}))


@router.post(
    "/restore/{resource_type}/{resource_id}",
    response_model=OperationResultResponse,
    summary="Restore an archived resource with identity verification (requires retention.restore)",
)
def restore_resource(
    resource_type: RetentionResourceType,
    resource_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> OperationResultResponse:
    if resource_type != RetentionResourceType.EVIDENCE:
        raise HTTPException(
            status_code=422,
            detail=f"Restore execution is not supported for {resource_type.value}",
        )
    _enforce_evidence_scope(db, request, principal, str(resource_id), "retention.restore")
    try:
        result = retention_service.restore_evidence(
            db, str(resource_id), _actor(principal))
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return OperationResultResponse(
        result=result["result"], operation_id=result.get("operation_id"),
        storage_key=result.get("storage_key"), evaluation=result.get("evaluation", {}))


@router.post(
    "/delete/{resource_type}/{resource_id}",
    response_model=OperationResultResponse,
    summary="Controlled two-phase deletion (requires retention.delete)",
)
def delete_resource(
    resource_type: RetentionResourceType,
    resource_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> OperationResultResponse:
    if resource_type != RetentionResourceType.EVIDENCE:
        raise HTTPException(
            status_code=422,
            detail=f"Deletion execution is not supported for {resource_type.value}",
        )
    _enforce_evidence_scope(db, request, principal, str(resource_id), "retention.delete")
    try:
        result = retention_service.delete_evidence(
            db, str(resource_id), _actor(principal))
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return OperationResultResponse(
        result=result["result"], operation_id=result.get("operation_id"),
        evaluation=result.get("evaluation", {}))


@router.get(
    "/operations",
    response_model=OperationListResponse,
    summary="List retention operations (requires retention.read)",
)
def list_operations(
    resource_type: RetentionResourceType | None = None,
    resource_id: UUID | None = None,
    operation: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_global("retention.read")),
) -> OperationListResponse:
    if operation is not None and operation not in ("ARCHIVE", "RESTORE", "DELETE"):
        raise HTTPException(status_code=422, detail="Unknown operation")
    if status is not None and status not in ("RUNNING", "COMPLETED", "FAILED"):
        raise HTTPException(status_code=422, detail="Unknown operation status")
    query = retention_repo.list_operations_query(
        db,
        resource_type=resource_type.value if resource_type else None,
        resource_id=str(resource_id) if resource_id else None,
        operation=operation, status=status,
    )
    rows = query.offset(offset).limit(limit).all()
    return OperationListResponse(
        items=[OperationResponse.model_validate(row) for row in rows],
        limit=limit, offset=offset, total=query.count())
