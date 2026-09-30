"""BE-016 identity and administration endpoints.

Development bearer tokens are accepted only when explicitly enabled;
production OIDC/OAuth2 plugs into principal resolution later. All
administrative mutations require GLOBAL-scoped permissions and emit
BE-015 audit events through the authorization service.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    Organization,
    OrganizationalUnit,
    Permission,
    Project,
    Role,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_db
from backend.repositories import authorization as auth_repo
from backend.schemas.authorization import (
    AdminProjectResponse,
    ApiClientCreate,
    ApiClientResponse,
    OrganizationCreate,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdate,
    OrganizationalUnitCreate,
    OrganizationalUnitListResponse,
    OrganizationalUnitResponse,
    OrganizationalUnitUpdate,
    PermissionResponse,
    PrincipalResponse,
    PrincipalType,
    ProjectOwnershipUpdate,
    ProjectScopeUpdate,
    RoleAssignmentCreate,
    RoleAssignmentListResponse,
    RoleAssignmentResponse,
    RoleResponse,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
)
from backend.security.authentication import get_current_principal, is_development_bypass
from backend.security.authorization import require, require_global
from backend.services import authorization as auth_service
from backend.services.authorization import AdminOperationError, Principal


router = APIRouter(prefix="/auth")


def _admin_actor(principal: Principal) -> Principal | None:
    """Containment-checked actor; None only for the explicit development bypass."""
    return None if is_development_bypass(principal) else principal


def _admin_error(error: AdminOperationError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


#: BE-025 §9: the administrative routes declare exactly the error statuses they
#: can actually return. 422 stays FastAPI's automatic request validation
#: response, so it is not repeated here.
_ERROR_RESPONSES = {
    401: "Authentication required (enforcing mode).",
    403: "Permission not held. GLOBAL-only guards reject a permission held in "
         "a narrower scope, as do the BE-025 containment rules (a GLOBAL target "
         "or an ADMINISTRATOR grant requires GLOBAL role.manage).",
    404: "Target absent, or foreign to the caller's scope. A resource outside "
         "the caller is reported exactly like a missing one so administrative "
         "endpoints cannot enumerate other organizations.",
    409: "Conflict. Either the resource being created already exists, or a "
         "deterministic administrative invariant refused the change (for "
         "example, removing the last active GLOBAL administrator).",
}


def _error_docs(*codes: int) -> dict[int, dict[str, str]]:
    return {code: {"description": _ERROR_RESPONSES[code]} for code in codes}


def _assignment_response(db: Session, row) -> RoleAssignmentResponse:
    role = auth_repo.roles_by_ids(db, [str(row.role_id)]).get(str(row.role_id))
    body = RoleAssignmentResponse.model_validate(row)
    body.role_name = role.name if role else None
    return body


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
    responses=_error_docs(401, 403, 409),
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
    responses=_error_docs(401, 403, 404),
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


@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List managed users (requires GLOBAL user.manage)",
    responses=_error_docs(401, 403),
)
def list_users(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_global("user.manage")),
    db: Session = Depends(get_db),
) -> UserListResponse:
    query = db.query(User).order_by(User.created_at, User.id)
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    user_ids = [str(row.id) for row in rows]
    assignments = (
        db.query(UserRoleAssignment)
        .filter(UserRoleAssignment.user_id.in_(user_ids)).all()
        if user_ids else []
    )
    role_rows = auth_repo.roles_by_ids(db, sorted({str(a.role_id) for a in assignments}))
    roles_by_user: dict[str, set[str]] = {}
    for assignment in assignments:
        role = role_rows.get(str(assignment.role_id))
        if role is not None:
            roles_by_user.setdefault(str(assignment.user_id), set()).add(role.name)
    items = []
    for row in rows:
        body = UserResponse.model_validate(row)
        body.roles = sorted(roles_by_user.get(str(row.id), set()))
        items.append(body)
    return UserListResponse(items=items, limit=limit, offset=offset, total=total)


@router.patch(
    "/users/{user_id}/status",
    response_model=UserResponse,
    summary="Suspend/disable/reactivate a user (requires GLOBAL user.manage; 409 when "
            "it would deactivate the last GLOBAL administrator)",
    responses=_error_docs(401, 403, 404, 409),
)
def update_user_status(
    user_id: UUID,
    payload: UserStatusUpdate,
    principal: Principal = Depends(require_global("user.manage")),
    db: Session = Depends(get_db),
) -> UserResponse:
    try:
        row = auth_service.set_user_status(
            db, user_id=str(user_id), status=payload.status.value,
            actor_id=_actor(principal))
    except AdminOperationError as error:
        raise _admin_error(error) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return UserResponse.model_validate(row)


@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization (requires organization.manage)",
    responses=_error_docs(401, 403),
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
    summary="Retrieve an organization (organization.manage must cover the organization)",
    responses=_error_docs(401, 403, 404),
)
def get_organization(
    organization_id: UUID,
    principal: Principal = Depends(require("organization.manage", "organization",
                                           "organization_id")),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    row = auth_repo.get_organization(db, str(organization_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationResponse.model_validate(row)


@router.get(
    "/organizations",
    response_model=OrganizationListResponse,
    summary="List organizations visible to the caller (requires organization.manage)",
    responses=_error_docs(401, 403),
)
def list_organizations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require("organization.manage")),
    db: Session = Depends(get_db),
) -> OrganizationListResponse:
    query = db.query(Organization).order_by(Organization.name, Organization.id)
    visible = auth_service.visible_organization_ids(db, _admin_actor(principal))
    if visible is not None:
        if not visible:
            return OrganizationListResponse(items=[], limit=limit, offset=offset, total=0)
        query = query.filter(Organization.id.in_(visible))
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return OrganizationListResponse(
        items=[OrganizationResponse.model_validate(row) for row in rows],
        limit=limit, offset=offset, total=total)


@router.patch(
    "/organizations/{organization_id}",
    response_model=OrganizationResponse,
    summary="Update an organization's name/status (code immutable; organization.manage "
            "must cover the organization)",
    responses=_error_docs(401, 403, 404),
)
def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    principal: Principal = Depends(require("organization.manage", "organization",
                                           "organization_id")),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    try:
        row = auth_service.update_organization(
            db, organization_id=str(organization_id), name=payload.name,
            status=payload.status, actor_id=_actor(principal))
    except AdminOperationError as error:
        raise _admin_error(error) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return OrganizationResponse.model_validate(row)


@router.post(
    "/organizations/{organization_id}/units",
    response_model=OrganizationalUnitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organizational unit (organization.manage covering the organization)",
    responses=_error_docs(401, 403, 404),
)
def create_unit(
    organization_id: UUID,
    payload: OrganizationalUnitCreate,
    principal: Principal = Depends(require("organization.manage", "organization",
                                           "organization_id")),
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
    response_model=OrganizationalUnitListResponse,
    summary="List units of an organization (organization.manage covering the organization)",
    responses=_error_docs(401, 403, 404),
)
def list_units(
    organization_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require("organization.manage", "organization",
                                           "organization_id")),
    db: Session = Depends(get_db),
) -> OrganizationalUnitListResponse:
    query = (
        db.query(OrganizationalUnit)
        .filter(OrganizationalUnit.organization_id == str(organization_id))
        .order_by(OrganizationalUnit.name, OrganizationalUnit.id)
    )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return OrganizationalUnitListResponse(
        items=[OrganizationalUnitResponse.model_validate(row) for row in rows],
        limit=limit, offset=offset, total=total)


@router.get(
    "/units/{unit_id}",
    response_model=OrganizationalUnitResponse,
    summary="Retrieve an organizational unit (organization.manage covering the unit)",
    responses=_error_docs(401, 403, 404),
)
def get_unit(
    unit_id: UUID,
    principal: Principal = Depends(require("organization.manage", "organizational_unit",
                                           "unit_id")),
    db: Session = Depends(get_db),
) -> OrganizationalUnitResponse:
    row = auth_repo.get_unit(db, str(unit_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Organizational unit not found")
    return OrganizationalUnitResponse.model_validate(row)


@router.patch(
    "/units/{unit_id}",
    response_model=OrganizationalUnitResponse,
    summary="Update a unit's name/status (organization membership is immutable)",
    responses=_error_docs(401, 403, 404),
)
def update_unit(
    unit_id: UUID,
    payload: OrganizationalUnitUpdate,
    principal: Principal = Depends(require("organization.manage", "organizational_unit",
                                           "unit_id")),
    db: Session = Depends(get_db),
) -> OrganizationalUnitResponse:
    try:
        row = auth_service.update_unit(
            db, unit_id=str(unit_id), name=payload.name, status=payload.status,
            actor_id=_actor(principal))
    except AdminOperationError as error:
        raise _admin_error(error) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return OrganizationalUnitResponse.model_validate(row)


@router.get(
    "/roles",
    response_model=list[RoleResponse],
    summary="List roles (requires role.manage)",
    responses=_error_docs(401, 403),
)
def list_roles(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_global("role.manage")),
    db: Session = Depends(get_db),
) -> list[RoleResponse]:
    rows = db.query(Role).order_by(Role.name).offset(offset).limit(limit).all()
    return [RoleResponse.model_validate(row) for row in rows]


@router.get(
    "/permissions",
    response_model=list[PermissionResponse],
    summary="List permissions (requires role.manage)",
    responses=_error_docs(401, 403),
)
def list_permissions(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_global("role.manage")),
    db: Session = Depends(get_db),
) -> list[PermissionResponse]:
    rows = db.query(Permission).order_by(Permission.name).offset(offset).limit(limit).all()
    return [PermissionResponse.model_validate(row) for row in rows]


@router.post(
    "/users/{user_id}/roles",
    response_model=RoleAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a scoped role (role.manage must cover the target scope; "
            "GLOBAL targets and ADMINISTRATOR require GLOBAL; 200 when already assigned)",
    responses=_error_docs(401, 403, 404),
)
def assign_role(
    user_id: UUID,
    payload: RoleAssignmentCreate,
    response: Response,
    principal: Principal = Depends(require("role.manage")),
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
            actor=_admin_actor(principal),
        )
    except AdminOperationError as error:
        raise _admin_error(error) from error
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


@router.get(
    "/users/{user_id}/roles",
    response_model=RoleAssignmentListResponse,
    summary="List a user's role assignments visible to the caller (requires role.manage)",
    responses=_error_docs(401, 403, 404),
)
def list_user_roles(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require("role.manage")),
    db: Session = Depends(get_db),
) -> RoleAssignmentListResponse:
    if auth_repo.get_user(db, str(user_id)) is None:
        raise HTTPException(status_code=404, detail="User not found")
    rows = auth_service.list_visible_assignments(
        db, user_id=str(user_id), actor=_admin_actor(principal))
    rows = sorted(rows, key=lambda row: (row.created_at, row.id))[offset:offset + limit]
    return RoleAssignmentListResponse(
        items=[_assignment_response(db, row) for row in rows],
        limit=limit, offset=offset, total=len(rows))


@router.delete(
    "/users/{user_id}/roles/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a role assignment (role.manage must cover the assignment scope; "
            "409 when it would remove the last GLOBAL administrator)",
    responses=_error_docs(401, 403, 404, 409),
)
def revoke_role(
    user_id: UUID,
    assignment_id: UUID,
    principal: Principal = Depends(require("role.manage")),
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
                                       actor_id=_actor(principal),
                                       actor=_admin_actor(principal))
    except AdminOperationError as error:
        raise _admin_error(error) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return None


@router.post(
    "/clients",
    response_model=ApiClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an API client with explicit scopes (requires user.manage)",
    responses=_error_docs(401, 403, 404, 409),
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


@router.patch(
    "/projects/{project_id}/scope",
    response_model=AdminProjectResponse,
    summary="Bind or clear a project's organization/unit (organization.manage must "
            "cover the project's current and destination scopes; clearing requires GLOBAL)",
    responses=_error_docs(401, 403, 404),
)
def update_project_scope(
    project_id: UUID,
    payload: ProjectScopeUpdate,
    principal: Principal = Depends(require("organization.manage", "project",
                                           "project_id")),
    db: Session = Depends(get_db),
) -> AdminProjectResponse:
    provided = payload.model_fields_set
    try:
        project = auth_service.change_project_scope(
            db, project_id=str(project_id),
            organization_id=(payload.organization_id if "organization_id" in provided
                             else auth_service.UNSET),
            organizational_unit_id=(
                payload.organizational_unit_id if "organizational_unit_id" in provided
                else auth_service.UNSET),
            actor=_admin_actor(principal),
            actor_id=_actor(principal),
        )
    except AdminOperationError as error:
        raise _admin_error(error) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return AdminProjectResponse.model_validate(project)


@router.post(
    "/projects/{project_id}/ownership",
    response_model=AdminProjectResponse,
    summary="Transfer project ownership to an active user (organization.manage must "
            "cover the project)",
    responses=_error_docs(401, 403, 404),
)
def transfer_project_ownership(
    project_id: UUID,
    payload: ProjectOwnershipUpdate,
    principal: Principal = Depends(require("organization.manage", "project",
                                           "project_id")),
    db: Session = Depends(get_db),
) -> AdminProjectResponse:
    try:
        project = auth_service.change_project_owner(
            db, project_id=str(project_id), owner_id=str(payload.owner_id),
            actor_id=_actor(principal))
    except AdminOperationError as error:
        raise _admin_error(error) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return AdminProjectResponse.model_validate(project)
