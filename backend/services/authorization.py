"""BE-016 centralized authorization service (no FastAPI dependency).

Evaluates ``can(principal, action, resource, context)`` deterministically
over database-resolved roles, permissions, and scopes. Order: principal
authentication state, principal status, required permission, role
assignment, organization scope, resource scope, contextual rules, final
decision. Any failed prerequisite short-circuits to deny (fail closed).

Roles grant permissions; scopes determine where they apply; neither
implies the other. In particular, administrative permissions never imply
substantive decision authority (``review_case.decide`` is a distinct
permission nothing administrative grants).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.models import (
    AUTH_PERMISSIONS,
    AUTH_ROLE_PERMISSIONS,
    AUTH_ROLES,
    Activity,
    ApiClient,
    Claim,
    Evidence,
    EvidenceRequest,
    FusionRun,
    Organization,
    OrganizationalUnit,
    Project,
    ReviewCase,
    User,
)
from backend.repositories import authorization as auth_repo


logger = logging.getLogger(__name__)

POLICY_VERSION = "auth-v1"

PERMISSIONS = frozenset(AUTH_PERMISSIONS)
ROLES = frozenset(AUTH_ROLES)

# Action -> required permission for endpoint wiring.
ACTION_PERMISSIONS = {
    "project.read": "project.read",
    "project.create": "project.create",
    "project.update": "project.update",
    "activity.read": "activity.read",
    "activity.create": "activity.create",
    "evidence.read": "evidence.read",
    "evidence.create": "evidence.create",
    "evidence.update_context": "evidence.update_context",
    "evidence.read_sensitive": "evidence.read_sensitive",
    "graph.read": "graph.read",
    "fusion.read": "fusion.read",
    "fusion.execute": "fusion.execute",
    "review_case.read": "review_case.read",
    "review_case.assign": "review_case.assign",
    "review_case.investigate": "review_case.investigate",
    "review_case.decide": "review_case.decide",
    "review_case.escalate": "review_case.escalate",
    "review_case.resolve": "review_case.resolve",
    "review_case.reopen": "review_case.reopen",
    "evidence_request.read": "evidence_request.read",
    "evidence_request.create": "evidence_request.create",
    "evidence_request.issue": "evidence_request.issue",
    "evidence_request.respond": "evidence_request.respond",
    "audit.read": "audit.read",
    "organization.manage": "organization.manage",
    "user.manage": "user.manage",
    "role.manage": "role.manage",
    "configuration.manage": "configuration.manage",
}


@dataclass(frozen=True)
class Scope:
    scope_type: str
    organization_id: str | None = None
    organizational_unit_id: str | None = None
    project_id: str | None = None


@dataclass(frozen=True)
class Principal:
    """Authenticated or explicitly anonymous actor (never FastAPI-bound)."""

    principal_id: str | None
    principal_type: str  # USER | API_CLIENT | SYSTEM | ANONYMOUS
    authenticated: bool
    status: str  # ACTIVE | SUSPENDED | DISABLED | ANONYMOUS
    display_name: str | None = None
    # permission -> scopes holding it.
    permissions: dict[str, tuple[Scope, ...]] = field(default_factory=dict)
    organization_ids: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Resource:
    resource_type: str
    resource_id: str | None = None
    project_id: str | None = None
    organization_id: str | None = None
    organizational_unit_id: str | None = None


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    permission: str
    scope: str | None = None
    policy_version: str = POLICY_VERSION


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def anonymous_principal() -> Principal:
    return Principal(
        principal_id=None, principal_type="ANONYMOUS", authenticated=False,
        status="ANONYMOUS",
    )


def ensure_default_catalogue(db: Session) -> None:
    """Seed baseline roles/permissions/mappings (idempotent; DB authoritative)."""
    for permission in AUTH_PERMISSIONS:
        auth_repo.ensure_permission(db, permission)
    for role, permissions in AUTH_ROLE_PERMISSIONS.items():
        role_row = auth_repo.ensure_role(db, role)
        for permission in permissions:
            permission_row = auth_repo.ensure_permission(db, permission)
            auth_repo.ensure_role_permission(db, role_row.id, permission_row.id)
    db.commit()


def _assignment_scope(assignment) -> Scope:
    return Scope(
        scope_type=assignment.scope_type,
        organization_id=str(assignment.organization_id) if assignment.organization_id else None,
        organizational_unit_id=str(assignment.organizational_unit_id)
        if assignment.organizational_unit_id else None,
        project_id=str(assignment.project_id) if assignment.project_id else None,
    )


def resolve_user_principal(db: Session, user_id: str) -> Principal:
    """Build a USER principal snapshot (2 batched queries + org/unit status)."""
    user = auth_repo.get_user(db, user_id)
    if user is None:
        return anonymous_principal()
    if user.status != "ACTIVE" or not user.is_active:
        return Principal(
            principal_id=str(user.id), principal_type="USER", authenticated=True,
            status=user.status if user.status in ("SUSPENDED", "DISABLED") else "DISABLED",
            display_name=user.display_name or user.username,
        )
    assignments = auth_repo.assignments_for_user(db, user.id)
    role_ids = sorted({str(a.role_id) for a in assignments})
    roles = auth_repo.roles_by_ids(db, role_ids)
    role_permissions = auth_repo.permissions_for_roles(db, role_ids)
    org_ids = {str(a.organization_id) for a in assignments if a.organization_id}
    unit_ids = {str(a.organizational_unit_id) for a in assignments if a.organizational_unit_id}
    org_status = (
        {str(o.id): o.status for o in db.query(Organization).filter(Organization.id.in_(org_ids)).all()}
        if org_ids else {}
    )
    unit_status = (
        {str(u.id): u.status for u in db.query(OrganizationalUnit).filter(OrganizationalUnit.id.in_(unit_ids)).all()}
        if unit_ids else {}
    )
    permissions: dict[str, list[Scope]] = {}
    organization_ids: set[str] = set()
    for assignment in assignments:
        role = roles.get(str(assignment.role_id))
        if role is None or role.status != "ACTIVE":
            continue
        if assignment.organization_id and org_status.get(str(assignment.organization_id)) != "ACTIVE":
            continue
        if assignment.organizational_unit_id and unit_status.get(
            str(assignment.organizational_unit_id)
        ) != "ACTIVE":
            continue
        scope = _assignment_scope(assignment)
        if scope.organization_id:
            organization_ids.add(scope.organization_id)
        for permission in sorted(role_permissions.get(str(assignment.role_id), ())):
            permissions.setdefault(permission, []).append(scope)
    return Principal(
        principal_id=str(user.id),
        principal_type="USER",
        authenticated=True,
        status="ACTIVE",
        display_name=user.display_name or user.username,
        permissions={key: tuple(value) for key, value in permissions.items()},
        organization_ids=tuple(sorted(organization_ids)),
    )


def resolve_client_principal(db: Session, client: ApiClient) -> Principal:
    """API clients carry explicit scopes (optionally project-bound)."""
    if client.status != "ACTIVE":
        return Principal(
            principal_id=str(client.id), principal_type="API_CLIENT",
            authenticated=True, status=client.status, display_name=client.name,
        )
    scopes = [str(scope) for scope in (client.scopes or []) if str(scope) in PERMISSIONS]
    scope = Scope(
        scope_type="PROJECT" if client.project_id else "GLOBAL",
        project_id=str(client.project_id) if client.project_id else None,
    )
    return Principal(
        principal_id=str(client.id),
        principal_type="API_CLIENT",
        authenticated=True,
        status="ACTIVE",
        display_name=client.name,
        permissions={permission: (scope,) for permission in scopes},
        scopes=tuple(scopes),
    )


def system_principal() -> Principal:
    return Principal(
        principal_id="system", principal_type="SYSTEM", authenticated=True,
        status="ACTIVE", display_name="system",
        permissions={permission: (Scope(scope_type="GLOBAL"),) for permission in PERMISSIONS},
    )


# ---------------------------------------------------------------------------
# Administrative operations (each audited; same-transaction semantics)
# ---------------------------------------------------------------------------


def _audit_admin(
    db: Session, event_type: str, action: str, resource_type: str,
    resource_id: str | None, actor_id: str | None, project_id: str | None,
    payload: dict,
) -> None:
    from backend.services import audit_ledger as audit_service

    audit_service.append_event(
        db, event_type=event_type, action=action, resource_type=resource_type,
        resource_id=resource_id, actor_id=actor_id, project_id=project_id,
        payload=payload, source="authorization_service",
    )


def create_user(
    db: Session, *, username: str, email: str, display_name: str | None = None,
    external_subject: str | None = None, identity_provider: str = "local",
    actor_id: str | None = None,
):
    """Create a managed user (USER_CREATED audit; no credentials stored)."""
    from uuid import UUID as _UUID

    if actor_id is not None:
        actor_id = str(_UUID(str(actor_id)))
    username, email = username.strip(), email.strip().lower()
    if not username or not email:
        raise ValueError("Username and email are required")
    row = auth_repo.insert_user(
        db, username=username, email=email, display_name=display_name,
        external_subject=external_subject or str(__import__("uuid").uuid4()),
        identity_provider=identity_provider,
    )
    _audit_admin(db, "USER_CREATED", "create", "users", row.id, actor_id, None,
                 {"user_id": row.id, "username": username})
    db.commit()
    db.refresh(row)
    return row


def create_organization(db: Session, *, name: str, code: str, actor_id: str | None = None):
    """Create an organization (ORGANIZATION_CREATED audit)."""
    from sqlalchemy.exc import IntegrityError as _IntegrityError

    if not name.strip() or not code.strip():
        raise ValueError("Organization name and code are required")
    try:
        row = auth_repo.insert_organization(db, name=name.strip(), code=code.strip())
        _audit_admin(db, "ORGANIZATION_CREATED", "create", "organizations", row.id,
                     actor_id, None, {"organization_id": row.id, "code": row.code})
        db.commit()
    except _IntegrityError as error:
        db.rollback()
        raise ValueError(f"Organization code already exists: {code.strip()}") from error
    db.refresh(row)
    return row


def create_organizational_unit(
    db: Session, *, organization_id: str, name: str, code: str,
    actor_id: str | None = None,
):
    """Create a unit inside an organization (UNIT_CREATED audit)."""
    from sqlalchemy.exc import IntegrityError as _IntegrityError

    organization_id = _require_uuid(organization_id, "organization_id")
    if auth_repo.get_organization(db, organization_id) is None:
        raise LookupError(f"Organization not found: {organization_id}")
    if not name.strip() or not code.strip():
        raise ValueError("Unit name and code are required")
    try:
        row = auth_repo.insert_unit(
            db, organization_id=organization_id, name=name.strip(), code=code.strip())
        _audit_admin(db, "ORGANIZATIONAL_UNIT_CREATED", "create", "organizational_units",
                     row.id, actor_id, None,
                     {"unit_id": row.id, "organization_id": organization_id})
        db.commit()
    except _IntegrityError as error:
        db.rollback()
        raise ValueError(f"Unit code already exists in organization: {code.strip()}") from error
    db.refresh(row)
    return row


def _require_uuid(value: str, label: str) -> str:
    from uuid import UUID as _UUID

    try:
        return str(_UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error


def assign_role(
    db: Session, *, user_id: str, role_name: str, scope_type: str,
    organization_id: str | None = None, organizational_unit_id: str | None = None,
    project_id: str | None = None, actor_id: str | None = None,
):
    """Assign a scoped role (ROLE_ASSIGNED audit; concurrent-safe, idempotent)."""
    from sqlalchemy.exc import IntegrityError as _IntegrityError

    from backend.db.models import OrganizationalUnit, Organization, Project

    user_id = _require_uuid(user_id, "user_id")
    if auth_repo.get_user(db, user_id) is None:
        raise LookupError(f"User not found: {user_id}")
    role = auth_repo.get_role_by_name(db, role_name)
    if role is None:
        raise LookupError(f"Role not found: {role_name}")
    if role.status != "ACTIVE":
        raise ValueError(f"Role is not active: {role_name}")
    if scope_type not in ("GLOBAL", "ORGANIZATION", "ORGANIZATIONAL_UNIT", "PROJECT"):
        raise ValueError(f"Unknown scope type: {scope_type!r}")
    organization_id = _require_uuid(organization_id, "organization_id") if organization_id else None
    organizational_unit_id = (
        _require_uuid(organizational_unit_id, "organizational_unit_id")
        if organizational_unit_id else None
    )
    project_id = _require_uuid(project_id, "project_id") if project_id else None
    if scope_type == "GLOBAL" and any((organization_id, organizational_unit_id, project_id)):
        raise ValueError("GLOBAL assignments must not carry scope identifiers")
    if scope_type == "ORGANIZATION":
        if organization_id is None or organizational_unit_id is not None or project_id is not None:
            raise ValueError("ORGANIZATION assignments require exactly organization_id")
        if auth_repo.get_organization(db, organization_id) is None:
            raise LookupError(f"Organization not found: {organization_id}")
    if scope_type == "ORGANIZATIONAL_UNIT":
        if organizational_unit_id is None or project_id is not None:
            raise ValueError("ORGANIZATIONAL_UNIT assignments require exactly organizational_unit_id")
        if auth_repo.get_unit(db, organizational_unit_id) is None:
            raise LookupError(f"Organizational unit not found: {organizational_unit_id}")
    if scope_type == "PROJECT":
        if project_id is None or organization_id is not None or organizational_unit_id is not None:
            raise ValueError("PROJECT assignments require exactly project_id")
        if db.query(Project).filter(Project.id == project_id).one_or_none() is None:
            raise LookupError(f"Project not found: {project_id}")
    try:
        row = auth_repo.insert_assignment(
            db, user_id=user_id, role_id=role.id, scope_type=scope_type,
            organization_id=organization_id,
            organizational_unit_id=organizational_unit_id, project_id=project_id,
        )
        _audit_admin(db, "ROLE_ASSIGNED", "assign", "user_role_assignments", row.id,
                     actor_id, project_id,
                     {"user_id": user_id, "role": role_name, "scope_type": scope_type,
                      "organization_id": organization_id,
                      "organizational_unit_id": organizational_unit_id,
                      "project_id": project_id})
        db.commit()
        created = True
    except _IntegrityError:
        db.rollback()
        from backend.db.models import UserRoleAssignment

        filters = [UserRoleAssignment.user_id == user_id,
                   UserRoleAssignment.role_id == role.id,
                   UserRoleAssignment.scope_type == scope_type]
        if organization_id is None:
            filters.append(UserRoleAssignment.organization_id.is_(None))
        else:
            filters.append(UserRoleAssignment.organization_id == organization_id)
        if organizational_unit_id is None:
            filters.append(UserRoleAssignment.organizational_unit_id.is_(None))
        else:
            filters.append(UserRoleAssignment.organizational_unit_id == organizational_unit_id)
        if project_id is None:
            filters.append(UserRoleAssignment.project_id.is_(None))
        else:
            filters.append(UserRoleAssignment.project_id == project_id)
        row = db.query(UserRoleAssignment).filter(*filters).one_or_none()
        if row is None:
            raise
        created = False
    db.refresh(row)
    return row, created


def revoke_assignment(db: Session, *, assignment_id: str, actor_id: str | None = None) -> None:
    """Revoke a role assignment (ROLE_REVOKED audit)."""
    from backend.db.models import UserRoleAssignment

    assignment_id = _require_uuid(assignment_id, "assignment_id")
    row = db.query(UserRoleAssignment).filter(UserRoleAssignment.id == assignment_id).one_or_none()
    if row is None:
        raise LookupError(f"Role assignment not found: {assignment_id}")
    snapshot = {"user_id": str(row.user_id), "role_id": str(row.role_id),
                "scope_type": row.scope_type, "project_id": str(row.project_id)
                if row.project_id else None}
    if not auth_repo.delete_assignment(db, assignment_id):
        raise LookupError(f"Role assignment not found: {assignment_id}")
    _audit_admin(db, "ROLE_REVOKED", "revoke", "user_role_assignments", assignment_id,
                 actor_id, snapshot["project_id"], snapshot)
    db.commit()


def create_api_client(
    db: Session, *, name: str, scopes: list[str], project_id: str | None = None,
    actor_id: str | None = None,
):
    """Register an API client with explicit scopes (no secret material in V1)."""
    from sqlalchemy.exc import IntegrityError as _IntegrityError

    if not name.strip():
        raise ValueError("Client name is required")
    clean = sorted({str(scope) for scope in (scopes or []) if str(scope) in PERMISSIONS})
    if not clean:
        raise ValueError("At least one known permission scope is required")
    if project_id is not None:
        from backend.db.models import Project

        project_id = _require_uuid(project_id, "project_id")
        if db.query(Project).filter(Project.id == project_id).one_or_none() is None:
            raise LookupError(f"Project not found: {project_id}")
    try:
        row = auth_repo.insert_client(db, name=name.strip(), scopes=clean, project_id=project_id)
        db.commit()
    except _IntegrityError as error:
        db.rollback()
        raise ValueError(f"API client name already exists: {name.strip()}") from error
    db.refresh(row)
    return row


def resolve_resource_scope(
    db: Session, resource_type: str, resource_id: str | None
) -> Resource:
    """Resolve a resource's organizational scope server-side (never trusted)."""
    if resource_id is None:
        return Resource(resource_type=resource_type)
    project_id: str | None = None
    organization_id: str | None = None
    unit_id: str | None = None
    if resource_type == "project":
        row = db.query(Project).filter(Project.id == resource_id).one_or_none()
        if row is None:
            return Resource(resource_type, resource_id)
        project_id, organization_id, unit_id = (
            str(row.id),
            str(row.organization_id) if row.organization_id else None,
            str(row.organizational_unit_id) if row.organizational_unit_id else None,
        )
    elif resource_type == "organization":
        row = db.query(Organization).filter(Organization.id == resource_id).one_or_none()
        if row is not None:
            organization_id = str(row.id)
    elif resource_type == "organizational_unit":
        row = db.query(OrganizationalUnit).filter(OrganizationalUnit.id == resource_id).one_or_none()
        if row is not None:
            unit_id, organization_id = str(row.id), str(row.organization_id)
    else:
        holder_project: str | None = None
        if resource_type == "activity":
            row = db.query(Activity).filter(Activity.id == resource_id).one_or_none()
            holder_project = str(row.project_id) if row else None
        elif resource_type == "claim":
            row = db.query(Claim).filter(Claim.id == resource_id).one_or_none()
            holder_project = str(row.project_id) if row else None
        elif resource_type == "evidence":
            row = db.query(Evidence).filter(Evidence.id == resource_id).one_or_none()
            holder_project = str(row.project_id) if row and row.project_id else None
        elif resource_type == "review_case":
            from backend.db.models import ReviewCase

            row = db.query(ReviewCase).filter(ReviewCase.id == resource_id).one_or_none()
            holder_project = str(row.project_id) if row and row.project_id else None
        elif resource_type == "evidence_request":
            from backend.db.models import EvidenceRequest

            row = db.query(EvidenceRequest).filter(EvidenceRequest.id == resource_id).one_or_none()
            holder_project = str(row.project_id) if row and row.project_id else None
        elif resource_type == "fusion_run":
            row = db.query(FusionRun).filter(FusionRun.id == resource_id).one_or_none()
            holder_project = None
            if row is not None:
                if row.target_type == "CLAIM":
                    claim = db.query(Claim).filter(Claim.id == row.target_id).one_or_none()
                    holder_project = str(claim.project_id) if claim else None
                elif row.target_type == "EVIDENCE":
                    evidence = db.query(Evidence).filter(Evidence.id == row.target_id).one_or_none()
                    holder_project = (
                        str(evidence.project_id) if evidence and evidence.project_id else None
                    )
        else:
            return Resource(resource_type, resource_id)
        if holder_project is not None:
            project = db.query(Project).filter(Project.id == holder_project).one_or_none()
            project_id = holder_project
            if project is not None:
                organization_id = (
                    str(project.organization_id) if project.organization_id else None
                )
                unit_id = (
                    str(project.organizational_unit_id) if project.organizational_unit_id else None
                )
    return Resource(
        resource_type=resource_type,
        resource_id=resource_id,
        project_id=project_id,
        organization_id=organization_id,
        organizational_unit_id=unit_id,
    )


def _scope_covers(assignment: Scope, resource: Resource) -> str | None:
    """Return scope description if the assignment covers the resource."""
    if assignment.scope_type == "GLOBAL":
        return "GLOBAL"
    if assignment.scope_type == "PROJECT":
        if resource.project_id and assignment.project_id == resource.project_id:
            return f"PROJECT:{resource.project_id}"
        return None
    if assignment.scope_type == "ORGANIZATION":
        # resource.organization_id is populated from the project chain, so
        # projects/units inside the organization are covered transitively.
        if resource.organization_id and assignment.organization_id == resource.organization_id:
            return f"ORGANIZATION:{resource.organization_id}"
        return None
    if assignment.scope_type == "ORGANIZATIONAL_UNIT":
        if resource.organizational_unit_id and (
            assignment.organizational_unit_id == resource.organizational_unit_id
        ):
            return f"ORGANIZATIONAL_UNIT:{resource.organizational_unit_id}"
        return None
    return None


def can(
    principal: Principal,
    action: str,
    resource: Resource,
    context: dict | None = None,
) -> AuthorizationDecision:
    """Central deterministic authorization decision (fail closed)."""
    permission = ACTION_PERMISSIONS.get(action, action)
    if not principal.authenticated:
        return AuthorizationDecision(False, "UNAUTHENTICATED", permission)
    if principal.status != "ACTIVE":
        return AuthorizationDecision(False, "PRINCIPAL_DISABLED", permission)
    if permission not in PERMISSIONS:
        return AuthorizationDecision(False, "UNKNOWN_PERMISSION", permission)
    scopes = principal.permissions.get(permission, ())
    if not scopes:
        return AuthorizationDecision(False, "NO_PERMISSION", permission)
    for scope in scopes:
        covered = _scope_covers(scope, resource)
        if covered is not None:
            return AuthorizationDecision(True, "ALLOWED", permission, covered)
    if (
        resource.project_id is None
        and resource.organization_id is None
        and resource.organizational_unit_id is None
        and resource.resource_id is not None
    ):
        return AuthorizationDecision(False, "RESOURCE_UNSCOPEABLE", permission)
    return AuthorizationDecision(False, "SCOPE_DENIED", permission)
