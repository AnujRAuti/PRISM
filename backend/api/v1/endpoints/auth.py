"""BE-016 identity and administration endpoints.

Development bearer tokens are accepted only when explicitly enabled;
production OIDC/OAuth2 plugs into principal resolution later. All
administrative mutations require GLOBAL-scoped permissions and emit
BE-015 audit events through the authorization service.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import OrganizationalUnit, Permission, Role
from backend.db.session import get_db
from backend.repositories import authorization as auth_repo
from backend.schemas.authorization import (
    ApiClientCreate,
    ApiClientResponse,
    OrganizationCreate,
    OrganizationalUnitCreate,
    OrganizationalUnitResponse,
    OrganizationResponse,
    PermissionResponse,
    PrincipalResponse,
    PrincipalType,
    RoleAssignmentCreate,
    RoleAssignmentResponse,
    RoleResponse,
    UserCreate,
    UserResponse,
)
from backend.security.authentication import get_current_principal
from backend.security.authorization import require_global
from backend.services import authorization as auth_service
from backend.services.authorization import Principal


router = APIRouter(prefix="/auth")


def _actor(principal: Principal) -> str | None:
    if principal.principal_type in ("USER", "API_CLIENT") and principal.principal_id:
        try:
            return str(UUID(principal.principal_id))
        except ValueError:
            return None
    return None


def _principal_response(db: Session, principal: Principal) -> PrincipalResponse:
    roles: list[str] = []
    permissions: list[str] = []
    if principal.principal_type == "USER" and principal.principal_id:
        assignments = auth_repo.assignments_for_user(db, principal.principal_id)
        role_rows = auth_repo.roles_by_ids(
            db, sorted({str(a.role_id) for a in assignments}))
        roles = sorted({role_rows[str(a.role_id)].name for a in assignments
                        if str(a.role_id) in role_rows})
        permissions = sorted(principal.permissions)
    elif principal.principal_type == "API_CLIENT":
        permissions = sorted(principal.permissions)
    return PrincipalResponse(
        id=UUID(principal.principal_id) if principal.principal_id else None,
        principal_type=PrincipalType(principal.principal_type),
        authenticated=principal.authenticated,
        status=principal.status,
        display_name=principal.display_name,
        roles=roles,
        permissions=permissions,
        organization_ids=[UUID(value) for value in principal.organization_ids],
        scopes=list(principal.scopes),
    )


@router.get(
    "/me",
    response_model=PrincipalResponse,
    summary="Current authenticated principal (401 anonymous in enforcing mode)",
)
def get_me(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> PrincipalResponse:
    return _principal_response(db, principal)


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a managed user (requires user.manage)",
    description="401 without credentials (enforcing mode). 403 without user.manage.",
)
def create_user(
    payload: UserCreate,
    principal: Principal = Depends(require_global("user.manage")),
    db: Session = Depends(get_db),
) -> UserResponse:
    try:
        row = auth_service.create_user(
            db, username=payload.username, email=payload.email,
            display_name=payload.display_name,
            external_subject=payload.external_subject,
            identity_provider=payload.identity_provider,
            actor_id=_actor(principal),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username, email, or identity already exists") from error
    return UserResponse.model_validate(row)


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="Retrieve a user (requires user.manage)",
)
def get_user(
    user_id: UUID,
    principal: Principal = Depends(require_global("user.manage")),
    db: Session = Depends(get_db),
) -> UserResponse:
    user = auth_repo.get_user(db, str(user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    assignments = auth_repo.assignments_for_user(db, user.id)
    role_rows = auth_repo.roles_by_ids(db, sorted({str(a.role_id) for a in assignments}))
    body = UserResponse.model_validate(user)
    body.roles = sorted({role_rows[str(a.role_id)].name for a in assignments
                         if str(a.role_id) in role_rows})
    return body


@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization (requires organization.manage)",
)
def create_organization(
    payload: OrganizationCreate,
    principal: Principal = Depends(require_global("organization.manage")),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    try:
        row = auth_service.create_organization(
            db, name=payload.name, code=payload.code, actor_id=_actor(principal))
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return OrganizationResponse.model_validate(row)


@router.get(
    "/organizations/{organization_id}",
    response_model=OrganizationResponse,
    summary="Retrieve an organization (requires organization.manage)",
)
def get_organization(
    organization_id: UUID,
    principal: Principal = Depends(require_global("organization.manage")),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    row = auth_repo.get_organization(db, str(organization_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationResponse.model_validate(row)


@router.post(
    "/organizations/{organization_id}/units",
    response_model=OrganizationalUnitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organizational unit (requires organization.manage)",
)
def create_unit(
    organization_id: UUID,
    payload: OrganizationalUnitCreate,
    principal: Principal = Depends(require_global("organization.manage")),
    db: Session = Depends(get_db),
) -> OrganizationalUnitResponse:
    try:
        row = auth_service.create_organizational_unit(
            db, organization_id=str(organization_id), name=payload.name,
            code=payload.code, actor_id=_actor(principal))
    except (ValueError, LookupError) as error:
        status_code = 404 if isinstance(error, LookupError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return OrganizationalUnitResponse.model_validate(row)


@router.get(
    "/organizations/{organization_id}/units",
    response_model=list[OrganizationalUnitResponse],
    summary="List units of an organization (requires organization.manage)",
)
def list_units(
    organization_id: UUID,
    principal: Principal = Depends(require_global("organization.manage")),
    db: Session = Depends(get_db),
) -> list[OrganizationalUnitResponse]:
    rows = (
        db.query(OrganizationalUnit)
        .filter(OrganizationalUnit.organization_id == str(organization_id))
        .order_by(OrganizationalUnit.created_at, OrganizationalUnit.id)
        .all()
    )
    return [OrganizationalUnitResponse.model_validate(row) for row in rows]


@router.get(
    "/roles",
    response_model=list[RoleResponse],
    summary="List roles (requires role.manage)",
)
def list_roles(
    principal: Principal = Depends(require_global("role.manage")),
    db: Session = Depends(get_db),
) -> list[RoleResponse]:
    rows = db.query(Role).order_by(Role.name).all()
    return [RoleResponse.model_validate(row) for row in rows]


@router.get(
    "/permissions",
    response_model=list[PermissionResponse],
    summary="List permissions (requires role.manage)",
)
def list_permissions(
    principal: Principal = Depends(require_global("role.manage")),
    db: Session = Depends(get_db),
) -> list[PermissionResponse]:
    rows = db.query(Permission).order_by(Permission.name).all()
    return [PermissionResponse.model_validate(row) for row in rows]


@router.post(
    "/users/{user_id}/roles",
    response_model=RoleAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a scoped role (requires role.manage; 200 when already assigned)",
)
def assign_role(
    user_id: UUID,
    payload: RoleAssignmentCreate,
    response: Response,
    principal: Principal = Depends(require_global("role.manage")),
    db: Session = Depends(get_db),
) -> RoleAssignmentResponse:
    try:
        row, created = auth_service.assign_role(
            db, user_id=str(user_id), role_name=payload.role_name,
            scope_type=payload.scope_type.value,
            organization_id=str(payload.organization_id) if payload.organization_id else None,
            organizational_unit_id=str(payload.organizational_unit_id)
            if payload.organizational_unit_id else None,
            project_id=str(payload.project_id) if payload.project_id else None,
            actor_id=_actor(principal),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    role = auth_repo.get_role_by_name(db, payload.role_name)
    body = RoleAssignmentResponse.model_validate(row)
    body.role_name = role.name if role else payload.role_name
    return body


@router.delete(
    "/users/{user_id}/roles/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a role assignment (requires role.manage)",
)
def revoke_role(
    user_id: UUID,
    assignment_id: UUID,
    principal: Principal = Depends(require_global("role.manage")),
    db: Session = Depends(get_db),
) -> None:
    from backend.db.models import UserRoleAssignment

    row = (
        db.query(UserRoleAssignment)
        .filter(UserRoleAssignment.id == str(assignment_id),
                UserRoleAssignment.user_id == str(user_id))
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    try:
        auth_service.revoke_assignment(db, assignment_id=str(assignment_id),
                                       actor_id=_actor(principal))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return None


@router.post(
    "/clients",
    response_model=ApiClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an API client with explicit scopes (requires user.manage)",
)
def create_client(
    payload: ApiClientCreate,
    principal: Principal = Depends(require_global("user.manage")),
    db: Session = Depends(get_db),
) -> ApiClientResponse:
    try:
        row = auth_service.create_api_client(
            db, name=payload.name, scopes=payload.scopes,
            project_id=str(payload.project_id) if payload.project_id else None,
            actor_id=_actor(principal),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="API client already exists") from error
    return ApiClientResponse.model_validate(row)
