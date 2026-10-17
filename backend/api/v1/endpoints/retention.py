"""BE-017 retention governance endpoints (policy-driven, fail-closed)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
    PolicyCreate,
    PolicyResponse,
    PolicyVersionCreate,
    PolicyVersionResponse,
    ResourceRetentionResponse,
    RetentionEvaluationResponse,
    RetentionResourceType,
    RetentionStateValue,
)
from backend.security.attribution import derive_actor
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


def _policy_readable(principal: Principal, policy) -> bool:
    """Whether this caller may read one retention policy row.

    A policy's own scope columns are the only authority on this: GLOBAL
    configuration is readable by anyone who holds ``retention.read`` at all
    (owner decision, acceptance register §8.1), and every other row is judged
    against its project / organization / organizational-unit scope by the
    central ``can()`` so a reviewer authorized for one project cannot read
    another project's retention rules.
    """
    from backend.security.authentication import is_development_bypass
    from backend.services.authorization import can

    if is_development_bypass(principal):
        return True
    if policy.scope_type == "GLOBAL":
        return "retention.read" in principal.permissions
    return can(
        principal,
        "retention.read",
        Resource(
            "retention",
            project_id=str(policy.project_id) if policy.project_id else None,
            organization_id=str(policy.organization_id) if policy.organization_id else None,
            organizational_unit_id=str(policy.organizational_unit_id)
            if policy.organizational_unit_id else None,
        ),
    ).allowed


@router.post(
    "/policies",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
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
    if row is None or not _policy_readable(principal, row):
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
    return [PolicyResponse.model_validate(row)
            for row in rows if _policy_readable(principal, row)]


@router.post(
    "/policies/{policy_id}/versions",
    response_model=PolicyVersionResponse,
    status_code=status.HTTP_201_CREATED,
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
    policy = retention_repo.get_policy(db, str(policy_id))
    if policy is None or not _policy_readable(principal, policy):
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
    from backend.schemas.retention import HoldResponse

    if status is not None and status not in retention_service.HOLD_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown hold status: {status!r}")
    # Authorized before paginated: a hold's project can only be known by
    # resolving its target, so slicing in SQL first would let a page come back
    # empty while readable rows sit beyond the offset.
    candidates = retention_repo.list_holds_query(
        db, status=status,
        project_id=str(project_id) if project_id else None,
    ).all()
    readable = [row for row in candidates if _hold_readable(db, principal, row)]
    return HoldListResponse(
        items=[HoldResponse.model_validate(row)
               for row in readable[offset:offset + limit]],
        limit=limit, offset=offset, total=len(readable))


def _resolve_hold_scope(
    db: Session,
    *,
    scope: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    project_id: str | None = None,
    claim_id: str | None = None,
    case_id: str | None = None,
    organization_id: str | None = None,
) -> dict:
    """Server-resolved scope for a hold, from its own target when not stated.

    A hold whose ``scope`` is CASE/CLAIM/RESOURCE names a target, not a project,
    so the project it belongs to has to be looked up. Both the write guard and
    the read filter use this one resolver: persisting what the guard authorized
    is what makes the row answerable to a scope check later.
    """
    resolved: dict[str, str | None] = {
        "project_id": project_id,
        "organization_id": organization_id,
        "organizational_unit_id": None,
    }
    if resolved["project_id"] is None:
        if scope == HoldScope.PROJECT.value and project_id:
            resolved["project_id"] = project_id
        elif scope == HoldScope.RESOURCE.value and resource_id:
            try:
                target = retention_service.resource_scope(
                    db, resource_type or "EVIDENCE", resource_id)
                resolved.update({key: target.get(key) for key in resolved})
            except (ValueError, LookupError):
                pass
        elif scope == HoldScope.CASE.value and case_id:
            from backend.db.models import ReviewCase

            case = db.query(ReviewCase).filter(
                ReviewCase.id == case_id).one_or_none()
            if case is not None and case.project_id:
                resolved["project_id"] = str(case.project_id)
        elif scope == HoldScope.CLAIM.value and claim_id:
            from backend.db.models import Claim

            claim = db.query(Claim).filter(
                Claim.id == claim_id).one_or_none()
            if claim is not None:
                resolved["project_id"] = str(claim.project_id)
        elif scope == HoldScope.ORGANIZATION.value and organization_id:
            resolved["organization_id"] = organization_id
    return resolved


def _hold_scope_for_row(db: Session, row) -> dict:
    """Resolve one persisted hold's scope, filling NULL columns from its target."""
    return _resolve_hold_scope(
        db,
        scope=row.scope,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        project_id=str(row.project_id) if row.project_id else None,
        claim_id=str(row.claim_id) if row.claim_id else None,
        case_id=str(row.case_id) if row.case_id else None,
        organization_id=str(row.organization_id) if row.organization_id else None,
    )


def _hold_readable(db: Session, principal: Principal, row) -> bool:
    """Whether this caller may read one hold row (fail closed when unresolvable)."""
    from backend.security.authentication import is_development_bypass
    from backend.services.authorization import can

    if is_development_bypass(principal):
        return True
    scope = _hold_scope_for_row(db, row)
    if not any(scope.values()):
        return False
    return can(principal, "retention.read", Resource(
        "retention",
        project_id=scope["project_id"],
        organization_id=scope["organization_id"],
        organizational_unit_id=scope["organizational_unit_id"],
    )).allowed


def _enforce_hold_scope(
    db: Session, request: Request, principal: Principal, payload: HoldCreate,
) -> dict:
    """Enforce hold creation against the hold's own scope (server-resolved)."""
    scope = _resolve_hold_scope(
        db,
        scope=payload.scope.value,
        resource_type=payload.resource_type.value if payload.resource_type else None,
        resource_id=str(payload.resource_id) if payload.resource_id else None,
        project_id=str(payload.project_id) if payload.project_id else None,
        claim_id=str(payload.claim_id) if payload.claim_id else None,
        case_id=str(payload.case_id) if payload.case_id else None,
        organization_id=str(payload.organization_id) if payload.organization_id else None,
    )
    _enforce_scope(db, request, principal, "retention.manage_hold", scope)
    return scope


@router.post(
    "/holds",
    response_model=HoldResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a hold (requires retention.manage_hold)",
)
def create_hold(
    payload: HoldCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> HoldResponse:
    scope = _enforce_hold_scope(db, request, principal, payload)
    try:
        row = retention_service.create_hold(
            db, scope=payload.scope.value, reason=payload.reason,
            resource_type=payload.resource_type.value if payload.resource_type else None,
            resource_id=str(payload.resource_id) if payload.resource_id else None,
            project_id=scope["project_id"],
            claim_id=str(payload.claim_id) if payload.claim_id else None,
            case_id=str(payload.case_id) if payload.case_id else None,
            organization_id=scope["organization_id"],
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
    if row is None or not _hold_readable(db, principal, row):
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
        _hold_scope_for_row(db, row),
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
            released_by=derive_actor(principal, payload.released_by, field="released_by"))
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
        # A completed deletion removes the evidence row, so the scope lookup that
        # authorizes the action cannot see it. BE-017 §52 requires a repeat delete
        # (and each losing racer in a concurrent delete) to converge on the
        # deterministic ALREADY_DELETED result rather than 404 -- that result is
        # produced by `delete_evidence`, so the guard must defer to the service
        # whenever a completed DELETE operation exists for this target. Any other
        # missing evidence remains a 404, and no scope decision is skipped: the
        # completed operation is only ever created by an already-authorized
        # deletion of this exact resource.
        if action == "retention.delete" and retention_repo.completed_delete_for(
                db, "EVIDENCE", evidence_id) is not None:
            return
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
