"""BE-016 authorization repository: persistence and lookups only.

All allow/deny evaluation lives in ``backend.services.authorization``.
"""

from sqlalchemy.orm import Session

from backend.db.models import (
    ApiClient,
    Organization,
    OrganizationalUnit,
    Permission,
    Role,
    RolePermission,
    User,
    UserRoleAssignment,
)


# -- organizations -----------------------------------------------------------

def insert_organization(db: Session, *, name: str, code: str) -> Organization:
    row = Organization(name=name, code=code)
    db.add(row)
    db.flush()
    return row


def get_organization(db: Session, organization_id: str) -> Organization | None:
    return db.query(Organization).filter(Organization.id == organization_id).one_or_none()


def insert_unit(db: Session, *, organization_id: str, name: str, code: str) -> OrganizationalUnit:
    row = OrganizationalUnit(organization_id=organization_id, name=name, code=code)
    db.add(row)
    db.flush()
    return row


def get_unit(db: Session, unit_id: str) -> OrganizationalUnit | None:
    return db.query(OrganizationalUnit).filter(OrganizationalUnit.id == unit_id).one_or_none()


# -- users -------------------------------------------------------------------

def get_user(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == user_id).one_or_none()


def insert_user(
    db: Session, *, username: str, email: str, display_name: str | None,
    external_subject: str, identity_provider: str,
) -> User:
    row = User(
        username=username,
        email=email,
        display_name=display_name or username,
        external_subject=external_subject,
        identity_provider=identity_provider,
        status="ACTIVE",
    )
    db.add(row)
    db.flush()
    return row


# -- roles / permissions ------------------------------------------------------

def get_role_by_name(db: Session, name: str) -> Role | None:
    return db.query(Role).filter(Role.name == name).one_or_none()


def get_permission_by_name(db: Session, name: str) -> Permission | None:
    return db.query(Permission).filter(Permission.name == name).one_or_none()


def ensure_role(db: Session, name: str, description: str | None = None) -> Role:
    row = get_role_by_name(db, name)
    if row is None:
        row = Role(name=name, description=description)
        db.add(row)
        db.flush()
    return row


def ensure_permission(db: Session, name: str, description: str | None = None) -> Permission:
    row = get_permission_by_name(db, name)
    if row is None:
        row = Permission(name=name, description=description)
        db.add(row)
        db.flush()
    return row


def ensure_role_permission(db: Session, role_id: str, permission_id: str) -> None:
    exists = (
        db.query(RolePermission)
        .filter(RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id)
        .one_or_none()
    )
    if exists is None:
        db.add(RolePermission(role_id=role_id, permission_id=permission_id))
        db.flush()


def insert_assignment(
    db: Session, *, user_id: str, role_id: str, scope_type: str,
    organization_id: str | None = None,
    organizational_unit_id: str | None = None,
    project_id: str | None = None,
) -> UserRoleAssignment:
    row = UserRoleAssignment(
        user_id=user_id,
        role_id=role_id,
        scope_type=scope_type,
        organization_id=organization_id,
        organizational_unit_id=organizational_unit_id,
        project_id=project_id,
    )
    db.add(row)
    db.flush()
    return row


def delete_assignment(db: Session, assignment_id: str) -> bool:
    row = (
        db.query(UserRoleAssignment)
        .filter(UserRoleAssignment.id == assignment_id)
        .one_or_none()
    )
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def assignments_for_user(db: Session, user_id: str) -> list[UserRoleAssignment]:
    return db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id).all()


def permissions_for_roles(db: Session, role_ids: list[str]) -> dict[str, set[str]]:
    """role_id -> permission names (active roles only matter to the caller)."""
    if not role_ids:
        return {}
    rows = (
        db.query(RolePermission.role_id, Permission.name)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .join(Role, Role.id == RolePermission.role_id)
        .filter(RolePermission.role_id.in_(role_ids), Role.status == "ACTIVE")
        .all()
    )
    mapping: dict[str, set[str]] = {}
    for role_id, permission_name in rows:
        mapping.setdefault(str(role_id), set()).add(str(permission_name))
    return mapping


def roles_by_ids(db: Session, role_ids: list[str]) -> dict[str, Role]:
    if not role_ids:
        return {}
    rows = db.query(Role).filter(Role.id.in_(role_ids)).all()
    return {row.id: row for row in rows}


# -- api clients --------------------------------------------------------------

def get_client(db: Session, client_id: str) -> ApiClient | None:
    return db.query(ApiClient).filter(ApiClient.id == client_id).one_or_none()


def insert_client(
    db: Session, *, name: str, scopes: list[str], project_id: str | None = None
) -> ApiClient:
    row = ApiClient(name=name, scopes=list(scopes), project_id=project_id)
    db.add(row)
    db.flush()
    return row
