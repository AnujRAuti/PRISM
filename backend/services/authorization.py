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
import re
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
    "retention.read": "retention.read",
    "retention.manage_policy": "retention.manage_policy",
    "retention.manage_hold": "retention.manage_hold",
    "retention.archive": "retention.archive",
    "retention.restore": "retention.restore",
    "retention.delete": "retention.delete",
    "notification.read": "notification.read",
    "notification.mark_read": "notification.mark_read",
    "notification.manage_preferences": "notification.manage_preferences",
    "notification.admin": "notification.admin",
    "integration.read": "integration.read",
    "integration.manage": "integration.manage",
    "api_client.manage": "api_client.manage",
    "credential.manage": "credential.manage",
    "external_data.read": "external_data.read",
    "external_data.write": "external_data.write",
    "webhook.manage": "webhook.manage",
    "webhook.read": "webhook.read",
    # BE-021 governance actions (§11)
    "dispute.create": "dispute.create",
    "dispute.read": "dispute.read",
    "dispute.review": "dispute.review",
    "dispute.resolve": "dispute.resolve",
    "correction.create": "correction.create",
    "correction.read": "correction.read",
    "correction.approve": "correction.approve",
    "correction.apply": "correction.apply",
    "intelligence.invalidate": "intelligence.invalidate",
    "intelligence.reprocess": "intelligence.reprocess",
    # BE-022 publication governance actions (§14)
    "publication.create": "publication.create",
    "publication.read": "publication.read",
    "publication.review": "publication.review",
    "publication.approve": "publication.approve",
    "publication.publish": "publication.publish",
    "publication.unpublish": "publication.unpublish",
    "publication.policy.manage": "publication.policy.manage",
    # BE-026 field operations actions
    "field.sync": "field.sync",
    "field_assignment.manage": "field_assignment.manage",
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


#: The database objects that make an identity attribute unique (BE-029
#: Option A). A violation of one of these is a conflict the caller can
#: correct; every other integrity failure is a defect behind the request and
#: must not be reported to the client as a duplicate identity.
IDENTITY_UNIQUE_OBJECTS = frozenset({
    "ix_users_username",
    "ix_users_email",
    "uq_user_identity_subject",
})


def identity_conflict(error) -> str | None:
    """Return the identity object the database refused, or ``None``.

    Keyed on the constraint/index name, not on the exception type:
    ``IntegrityError`` also wraps NOT NULL, foreign-key and primary-key
    failures, and a blanket ``IntegrityError`` -> 409 would dress those up as
    duplicate identities.
    """
    orig = getattr(error, "orig", None)
    name = getattr(getattr(orig, "diag", None), "constraint_name", None)
    if name is None:
        match = re.search(r'unique constraint "([^"]+)"', str(orig), re.IGNORECASE)
        name = match.group(1) if match else None
    return name if name in IDENTITY_UNIQUE_OBJECTS else None


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


def _lock_row(db: Session, model, row_id: str):
    """Read one row under a row lock for an audited mutation.

    Every audited mutation here computes a ``before``/``after`` delta, so the
    read must serialize with concurrent writers to the same row: an unlocked
    read lets two writers both report the same predecessor, lets a writer audit
    a transition another transaction already committed, and lets a revocation
    delete a row that a concurrent revocation already removed.
    """
    return (db.query(model).filter(model.id == row_id)
            .with_for_update().one_or_none())


def assign_role(
    db: Session, *, user_id: str, role_name: str, scope_type: str,
    organization_id: str | None = None, organizational_unit_id: str | None = None,
    project_id: str | None = None, actor_id: str | None = None,
    actor: Principal | None = None,
):
    """Assign a scoped role (ROLE_ASSIGNED audit; concurrent-safe, idempotent).

    ``actor`` (when provided) is checked against the BE-025 containment rules:
    E1 — GLOBAL-scope assignments and any assignment of ADMINISTRATOR require
    GLOBAL role.manage; E2 — role.manage must cover the target scope (foreign
    targets deny as 404, matching BE-016 indistinguishability). ``actor=None``
    is reserved for internal/system callers (seeding, tests, development-mode
    bypass) exactly as before this milestone.
    """
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
    if actor is not None:
        if scope_type == "GLOBAL":
            if not _holds_global(actor, "role.manage"):
                raise AdminOperationError(
                    403, "GLOBAL-scope assignments require GLOBAL role.manage authority")
        else:
            target = _assignment_target_resource(
                db, scope_type, organization_id=organization_id,
                organizational_unit_id=organizational_unit_id, project_id=project_id)
            decision = can(actor, "role.manage", target)
            if not decision.allowed:
                raise _deny_for(decision)
        if role_name == "ADMINISTRATOR" and not _holds_global(actor, "role.manage"):
            raise AdminOperationError(
                403, "Assigning ADMINISTRATOR requires GLOBAL role.manage authority")
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


def revoke_assignment(db: Session, *, assignment_id: str, actor_id: str | None = None,
                      actor: Principal | None = None) -> None:
    """Revoke a role assignment (ROLE_REVOKED audit).

    ``actor`` (when provided) must hold role.manage covering the assignment's
    own scope (E2), and revoking the last active GLOBAL ADMINISTRATOR
    assignment is refused with 409 under a transaction-scoped advisory lock
    so concurrent second-to-last revocations serialize deterministically.
    """
    from backend.db.models import Role as RoleModel
    from backend.db.models import UserRoleAssignment

    assignment_id = _require_uuid(assignment_id, "assignment_id")
    row = _lock_row(db, UserRoleAssignment, assignment_id)
    if row is None:
        raise LookupError(f"Role assignment not found: {assignment_id}")
    if actor is not None:
        if row.scope_type == "GLOBAL":
            if not _holds_global(actor, "role.manage"):
                raise AdminOperationError(
                    403, "GLOBAL-scope assignments require GLOBAL role.manage authority")
        else:
            target = _assignment_target_resource(
                db, row.scope_type,
                organization_id=str(row.organization_id) if row.organization_id else None,
                organizational_unit_id=str(row.organizational_unit_id)
                if row.organizational_unit_id else None,
                project_id=str(row.project_id) if row.project_id else None)
            decision = can(actor, "role.manage", target)
            if not decision.allowed:
                raise _deny_for(decision)
    role_row = db.query(RoleModel).filter(RoleModel.id == row.role_id).one_or_none()
    if (role_row is not None and role_row.name == "ADMINISTRATOR"
            and row.scope_type == "GLOBAL"):
        _lock_last_admin(db)
        if _would_leave_no_global_administrator(db, str(row.user_id),
                                                exclude_assignment_id=str(row.id)):
            raise AdminOperationError(
                409, "Cannot revoke the last active GLOBAL administrator")
    snapshot = {"user_id": str(row.user_id), "role_id": str(row.role_id),
                "scope_type": row.scope_type, "project_id": str(row.project_id)
                if row.project_id else None}
    if not auth_repo.delete_assignment(db, assignment_id):
        raise LookupError(f"Role assignment not found: {assignment_id}")
    _audit_admin(db, "ROLE_REVOKED", "revoke", "user_role_assignments", assignment_id,
                 actor_id, snapshot["project_id"], snapshot)
    db.commit()


UNSET = object()


def update_organization(db: Session, *, organization_id: str,
                        name: str | None = None, status: str | None = None,
                        actor_id: str | None = None):
    """Update an organization's name/status (code immutable; audited no-op-free)."""
    organization_id = _require_uuid(organization_id, "organization_id")
    row = _lock_row(db, Organization, organization_id)
    if row is None:
        raise LookupError(f"Organization not found: {organization_id}")
    if name is not None and not name.strip():
        raise ValueError("Organization name must not be blank")
    if status is not None and status not in USER_STATUS_VALUES:
        raise ValueError(f"Unknown organization status: {status!r}")
    before = {"name": row.name, "status": row.status}
    if name is not None:
        row.name = name.strip()
    if status is not None:
        row.status = status
    after = {"name": row.name, "status": row.status}
    if before == after:
        return row
    _audit_admin(db, "ORGANIZATION_UPDATED", "update", "organizations",
                 organization_id, actor_id, None,
                 {"organization_id": organization_id, "before": before, "after": after})
    db.commit()
    db.refresh(row)
    return row


def update_unit(db: Session, *, unit_id: str, name: str | None = None,
                status: str | None = None, actor_id: str | None = None):
    """Update a unit's name/status (organization membership immutable; audited)."""
    unit_id = _require_uuid(unit_id, "unit_id")
    row = _lock_row(db, OrganizationalUnit, unit_id)
    if row is None:
        raise LookupError(f"Organizational unit not found: {unit_id}")
    if name is not None and not name.strip():
        raise ValueError("Unit name must not be blank")
    if status is not None and status not in USER_STATUS_VALUES:
        raise ValueError(f"Unknown unit status: {status!r}")
    before = {"name": row.name, "status": row.status}
    if name is not None:
        row.name = name.strip()
    if status is not None:
        row.status = status
    after = {"name": row.name, "status": row.status}
    if before == after:
        return row
    _audit_admin(db, "ORGANIZATIONAL_UNIT_UPDATED", "update", "organizational_units",
                 unit_id, actor_id, None,
                 {"unit_id": unit_id, "organization_id": str(row.organization_id),
                  "before": before, "after": after})
    db.commit()
    db.refresh(row)
    return row


def set_user_status(db: Session, *, user_id: str, status: str,
                    actor_id: str | None = None):
    """Suspend/disable/reactivate a managed user (audited; last-admin guarded).

    ``is_active`` mirrors the ACTIVE state so both existing gates in
    ``resolve_user_principal`` stay consistent. Revoking access is immediate:
    principals are rebuilt per request from the database.
    """
    from backend.db.models import User

    user_id = _require_uuid(user_id, "user_id")
    if status not in USER_STATUS_VALUES:
        raise ValueError(f"Unknown user status: {status!r}")
    row = _lock_row(db, User, user_id)
    if row is None:
        raise LookupError(f"User not found: {user_id}")
    if row.status == status and row.is_active == (status == "ACTIVE"):
        return row
    if status != "ACTIVE":
        _lock_last_admin(db)
        if _would_leave_no_global_administrator(db, user_id, None, removes_user=True):
            raise AdminOperationError(
                409, "Cannot deactivate the last active GLOBAL administrator")
    before = row.status
    row.status = status
    row.is_active = status == "ACTIVE"
    _audit_admin(db, "USER_STATUS_CHANGED", "update", "users", user_id, actor_id, None,
                 {"user_id": user_id, "status": {"before": before, "after": status}})
    db.commit()
    db.refresh(row)
    return row


def visible_organization_ids(db: Session, actor: Principal | None) -> set[str] | None:
    """Organizations an actor may administer (None = all; unit grants include parent)."""
    if actor is None:
        return None
    scopes = actor.permissions.get("organization.manage", ())
    ids: set[str] = set()
    for scope in scopes:
        if scope.scope_type == "GLOBAL":
            return None
        if scope.scope_type == "ORGANIZATION" and scope.organization_id:
            ids.add(scope.organization_id)
        elif scope.scope_type == "ORGANIZATIONAL_UNIT" and scope.organizational_unit_id:
            unit = auth_repo.get_unit(db, scope.organizational_unit_id)
            if unit is not None:
                ids.add(str(unit.organization_id))
    return ids


def list_visible_assignments(db: Session, *, user_id: str,
                             actor: Principal | None) -> list:
    """Assignments of a user visible to the actor (role.manage must cover each)."""
    user_id = _require_uuid(user_id, "user_id")
    rows = auth_repo.assignments_for_user(db, user_id)
    if actor is None:
        return rows
    visible = []
    for row in rows:
        target = _assignment_target_resource(
            db, row.scope_type,
            organization_id=str(row.organization_id) if row.organization_id else None,
            organizational_unit_id=str(row.organizational_unit_id)
            if row.organizational_unit_id else None,
            project_id=str(row.project_id) if row.project_id else None)
        if can(actor, "role.manage", target).allowed:
            visible.append(row)
    return visible


def change_project_scope(db: Session, *, project_id: str,
                         organization_id=UNSET, organizational_unit_id=UNSET,
                         actor: Principal | None = None, actor_id: str | None = None):
    """Bind/clear a project's organization/unit (E2/E4; audited; no partial state).

    Destination authority: binding or rebinding requires organization.manage
    covering the destination org/unit; clearing any binding requires a GLOBAL
    grant; the endpoint-level require() already pins authority over the
    project's *current* scope (so initially unscoped projects escape every
    non-GLOBAL caller there).
    """
    project = _lock_row(db, Project, project_id)
    if project is None:
        raise LookupError(f"Project not found: {project_id}")
    current_org = str(project.organization_id) if project.organization_id else None
    current_unit = (str(project.organizational_unit_id)
                    if project.organizational_unit_id else None)
    new_org = (current_org if organization_id is UNSET
               else _require_uuid(organization_id, "organization_id")
               if organization_id is not None else None)
    new_unit = (current_unit if organizational_unit_id is UNSET
                else _require_uuid(organizational_unit_id, "organizational_unit_id")
                if organizational_unit_id is not None else None)
    if new_org == current_org and new_unit == current_unit:
        return project
    if new_unit is not None and new_org is None:
        raise ValueError("A project in an organizational unit must name its organization")
    if (new_org is None and current_org is not None) or (
            new_unit is None and current_unit is not None):
        if actor is not None and not _holds_global(actor, "organization.manage"):
            raise AdminOperationError(
                403, "Clearing a project's organizational scope requires GLOBAL authority")
    if new_org is not None and new_org != current_org:
        org_row = auth_repo.get_organization(db, new_org)
        if org_row is None:
            raise LookupError(f"Organization not found: {new_org}")
        if org_row.status != "ACTIVE":
            raise ValueError("Cannot bind a project to an inactive organization")
        if actor is not None:
            decision = can(actor, "organization.manage",
                           Resource("organization", resource_id=new_org,
                                    organization_id=new_org))
            if not decision.allowed:
                raise _deny_for(decision)
    if new_unit is not None:
        unit_row = auth_repo.get_unit(db, new_unit)
        if unit_row is None:
            raise LookupError(f"Organizational unit not found: {new_unit}")
        # Validated even when the unit itself is unchanged: rebinding only the
        # organization must never leave the project inside a foreign unit.
        if str(unit_row.organization_id) != new_org:
            raise ValueError("Organizational unit does not belong to the organization")
        if unit_row.status != "ACTIVE":
            raise ValueError("Cannot bind a project to an inactive organizational unit")
        if new_unit != current_unit and actor is not None:
            decision = can(actor, "organization.manage",
                           Resource("organizational_unit", resource_id=new_unit,
                                    organizational_unit_id=new_unit,
                                    organization_id=new_org))
            if not decision.allowed:
                raise _deny_for(decision)
    project.organization_id = new_org
    project.organizational_unit_id = new_unit
    _audit_admin(db, "PROJECT_SCOPE_CHANGED", "update", "projects", project_id,
                 actor_id, project_id,
                 {"project_id": project_id,
                  "before": {"organization_id": current_org,
                             "organizational_unit_id": current_unit},
                  "after": {"organization_id": new_org,
                            "organizational_unit_id": new_unit}})
    db.commit()
    db.refresh(project)
    return project


def change_project_owner(db: Session, *, project_id: str, owner_id: str,
                         actor_id: str | None = None):
    """Transfer project ownership to an active user (audited)."""
    from backend.db.models import User

    project = _lock_row(db, Project, project_id)
    if project is None:
        raise LookupError(f"Project not found: {project_id}")
    owner_id = _require_uuid(owner_id, "owner_id")
    new_owner = db.query(User).filter(User.id == owner_id).one_or_none()
    if new_owner is None:
        raise LookupError(f"User not found: {owner_id}")
    if new_owner.status != "ACTIVE" or not new_owner.is_active:
        raise ValueError("New owner must be an active user")
    current_owner = str(project.owner_id)
    if current_owner == owner_id:
        return project
    project.owner_id = owner_id
    _audit_admin(db, "PROJECT_OWNERSHIP_CHANGED", "update", "projects", project_id,
                 actor_id, project_id,
                 {"project_id": project_id,
                  "owner_id": {"before": current_owner, "after": owner_id}})
    db.commit()
    db.refresh(project)
    return project


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


class AdminOperationError(Exception):
    """BE-025 deterministic administrative denial carrying its HTTP mapping."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


USER_STATUS_VALUES = ("ACTIVE", "SUSPENDED", "DISABLED")

# Fixed namespace key for pg_advisory_xact_lock guarding last-administrator
# removal; every revocation/deactivation serializes on this single lock.
_LAST_ADMIN_LOCK_KEY = 0x504F413235


def _deny_for(decision: AuthorizationDecision) -> AdminOperationError:
    """Map a containment denial like enforce() does (out-of-scope -> 404)."""
    if decision.reason in ("SCOPE_DENIED", "RESOURCE_UNSCOPEABLE"):
        return AdminOperationError(404, "Not found")
    if decision.reason == "UNAUTHENTICATED":
        return AdminOperationError(401, "Authentication required")
    return AdminOperationError(403, "Forbidden")


def _holds_global(actor: Principal, permission: str) -> bool:
    return any(
        scope.scope_type == "GLOBAL" for scope in actor.permissions.get(permission, ())
    )


def _assignment_target_resource(
    db: Session, scope_type: str,
    organization_id: str | None = None,
    organizational_unit_id: str | None = None,
    project_id: str | None = None,
) -> Resource:
    """The resource an actor's role.manage grant must cover for an operation."""
    if scope_type == "GLOBAL":
        return Resource("global")
    if scope_type == "ORGANIZATION":
        return Resource("organization", resource_id=organization_id,
                        organization_id=organization_id)
    if scope_type == "ORGANIZATIONAL_UNIT":
        unit = auth_repo.get_unit(db, organizational_unit_id) if organizational_unit_id else None
        return Resource("organizational_unit", resource_id=organizational_unit_id,
                        organizational_unit_id=organizational_unit_id,
                        organization_id=str(unit.organization_id) if unit else None)
    return resolve_resource_scope(db, "project", project_id)


def _lock_last_admin(db: Session) -> None:
    from sqlalchemy import text

    db.execute(text("SELECT pg_advisory_xact_lock(:key)"),
               {"key": _LAST_ADMIN_LOCK_KEY})


def _active_global_administrators(db: Session) -> dict[str, int]:
    """user_id -> count of ACTIVE GLOBAL ADMINISTRATOR assignments."""
    from backend.db.models import Role as RoleModel
    from backend.db.models import User as UserModel
    from backend.db.models import UserRoleAssignment

    rows = (
        db.query(UserRoleAssignment.user_id)
        .join(RoleModel, RoleModel.id == UserRoleAssignment.role_id)
        .join(UserModel, UserModel.id == UserRoleAssignment.user_id)
        .filter(UserRoleAssignment.scope_type == "GLOBAL",
                RoleModel.name == "ADMINISTRATOR",
                RoleModel.status == "ACTIVE",
                UserModel.status == "ACTIVE",
                UserModel.is_active.is_(True))
        .all()
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row[0])] = counts.get(str(row[0]), 0) + 1
    return counts


def _would_leave_no_global_administrator(db: Session, user_id: str,
                                         exclude_assignment_id: str | None,
                                         removes_user: bool = False) -> bool:
    """Would the operation leave zero active GLOBAL administrators?

    ``exclude_assignment_id`` removes a single assignment (revocation);
    ``removes_user`` removes every grant the user holds (deactivation), which
    is why a lone admin holding several GLOBAL assignments is still the last
    one.
    """
    counts = _active_global_administrators(db)
    if user_id not in counts:
        return False
    if any(key != user_id for key in counts):
        return False
    if removes_user:
        return True
    remaining = counts[user_id] - (1 if exclude_assignment_id else 0)
    return remaining <= 0


def governance_target_resource(target_type: str | None) -> str | None:
    """BE-021 dispute/invalidation target type -> resolvable resource type.

    Returns ``None`` for unknown types so callers stay fail-closed (an
    unresolvable target yields an unscopeable resource rather than a leak).
    """
    return {
        "EVIDENCE": "evidence",
        "CLAIM": "claim",
        "REVIEW_CASE": "review_case",
        "EVIDENCE_CLAIM_RELATIONSHIP": "graph_relationship",
        "FUSION_ASSESSMENT": "integrity_assessment",
        "EXTERNAL_ASSERTION": "external_assertion",
    }.get(target_type or "")


def publication_target_resource(target_type: str | None) -> str | None:
    """BE-022 publication target type -> resolvable resource type.

    Returns ``None`` for unknown types so an unresolvable target yields an
    unscopeable resource rather than a scope leak.
    """
    return {
        "PROJECT": "project",
        "ACTIVITY": "activity",
        "CLAIM": "claim",
        "EVIDENCE": "evidence",
        "REVIEW_CASE": "review_case",
        "FUSION_ASSESSMENT": "integrity_assessment",
    }.get(target_type or "")


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
        elif resource_type == "notification":
            from backend.db.models import Notification

            row = db.query(Notification).filter(Notification.id == resource_id).one_or_none()
            holder_project = str(row.project_id) if row and row.project_id else None
        elif resource_type == "external_system":
            from backend.db.models import ExternalSystem

            row = db.query(ExternalSystem).filter(ExternalSystem.id == resource_id).one_or_none()
            if row is not None and row.organization_id:
                organization_id = str(row.organization_id)
        elif resource_type == "api_client":
            from backend.db.models import ApiClient

            row = db.query(ApiClient).filter(ApiClient.id == resource_id).one_or_none()
            holder_project = str(row.project_id) if row and row.project_id else None
        elif resource_type == "webhook_subscription":
            from backend.db.models import ExternalSystem, WebhookSubscription

            row = db.query(WebhookSubscription).filter(WebhookSubscription.id == resource_id).one_or_none()
            if row is not None:
                ext_sys = db.query(ExternalSystem).filter(ExternalSystem.id == row.external_system_id).one_or_none()
                if ext_sys and ext_sys.organization_id:
                    organization_id = str(ext_sys.organization_id)
        elif resource_type == "dispute":
            # BE-021: disputes carry their (possibly null) project scope; when
            # the target itself is not project-scoped (fusion assessment,
            # graph relationship, external assertion), scope derives from the
            # target so the governance workflow stays reachable.
            from backend.db.models import Dispute

            row = db.query(Dispute).filter(Dispute.id == resource_id).one_or_none()
            holder_project = str(row.project_id) if row and row.project_id else None
            if row is not None and holder_project is None:
                target_resource = governance_target_resource(row.target_type)
                if target_resource is not None:
                    return resolve_resource_scope(db, target_resource, str(row.target_id))
        elif resource_type == "correction_request":
            from backend.db.models import CorrectionRequest

            row = db.query(CorrectionRequest).filter(CorrectionRequest.id == resource_id).one_or_none()
            holder_project = str(row.project_id) if row and row.project_id else None
            if row is not None and holder_project is None:
                # Corrections only target evidence; fall back to its project.
                return resolve_resource_scope(db, "evidence", str(row.target_id))
        elif resource_type == "reprocessing_request":
            from backend.db.models import ReprocessingRequest

            row = db.query(ReprocessingRequest).filter(ReprocessingRequest.id == resource_id).one_or_none()
            holder_project = str(row.project_id) if row and row.project_id else None
            if row is not None and holder_project is None:
                # Reprocessing only applies to evidence; fall back to its project.
                return resolve_resource_scope(db, "evidence", str(row.evidence_id))
        elif resource_type == "publication":
            # BE-022: a publication is scoped through its target so that a
            # project-scoped grant reaches it, and an unscoped target stays
            # unscoped (fail-closed) rather than being world-readable.
            from backend.db.models import Publication

            row = db.query(Publication).filter(Publication.id == resource_id).one_or_none()
            if row is not None:
                return resolve_resource_scope(
                    db, publication_target_resource(row.target_type), str(row.target_id)
                )
        elif resource_type == "publication_policy":
            # BE-022: policies are administrative configuration, not scoped
            # domain objects. They resolve to a bare resource so only GLOBAL
            # assignments can manage them.
            return Resource(resource_type, resource_id)
        elif resource_type == "intelligence_invalidation":
            from backend.db.models import IntelligenceInvalidation

            row = db.query(IntelligenceInvalidation).filter(
                IntelligenceInvalidation.id == resource_id
            ).one_or_none()
            holder_project = str(row.project_id) if row and row.project_id else None
            if row is not None and holder_project is None:
                target_resource = governance_target_resource(row.target_type)
                if target_resource is not None:
                    return resolve_resource_scope(db, target_resource, str(row.target_id))
        elif resource_type == "graph_relationship":
            # BE-021: scope a relationship by its endpoint nodes' owning
            # projects (the same resolution the graph list filter uses).
            from backend.db.models import GraphNode, GraphRelationship
            from backend.services import evidence_graph as graph_service

            row = (
                db.query(GraphRelationship)
                .filter(GraphRelationship.id == resource_id)
                .one_or_none()
            )
            if row is not None:
                nodes = (
                    db.query(GraphNode)
                    .filter(GraphNode.id.in_({row.source_node_id, row.target_node_id}))
                    .all()
                )
                projects = graph_service._node_project_map(db, nodes)
                endpoint_projects = {projects.get(node.id) for node in nodes} - {None}
                if len(endpoint_projects) == 1:
                    holder_project = next(iter(endpoint_projects))
                elif len(endpoint_projects) > 1:
                    # Cross-project edge: fall back to the source's project so
                    # a single project grant cannot authorize it silently.
                    source_project = projects.get(row.source_node_id)
                    holder_project = source_project
        elif resource_type == "integrity_assessment":
            # BE-021: scope an assessment through its fusion run's target.
            from backend.db.models import IntegrityAssessment

            row = (
                db.query(IntegrityAssessment)
                .filter(IntegrityAssessment.id == resource_id)
                .one_or_none()
            )
            if row is not None:
                return resolve_resource_scope(db, "fusion_run", str(row.fusion_run_id))
        elif resource_type == "external_assertion":
            # BE-021: assertions belong to an external system's organization.
            from backend.db.models import ExternalAssertion, ExternalSystem

            row = (
                db.query(ExternalAssertion)
                .filter(ExternalAssertion.id == resource_id)
                .one_or_none()
            )
            if row is not None:
                ext_sys = (
                    db.query(ExternalSystem)
                    .filter(ExternalSystem.id == row.external_system_id)
                    .one_or_none()
                )
                if ext_sys and ext_sys.organization_id:
                    organization_id = str(ext_sys.organization_id)
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
