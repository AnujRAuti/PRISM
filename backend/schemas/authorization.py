"""BE-016 Pydantic v2 schemas for identity, RBAC, and decisions.

Never carries password/secret material: V1 has no credentials to expose
(development bearer tokens are non-secret identifiers).
"""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PrincipalType(str, Enum):
    USER = "USER"
    API_CLIENT = "API_CLIENT"
    SYSTEM = "SYSTEM"
    ANONYMOUS = "ANONYMOUS"


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


class ScopeType(str, Enum):
    GLOBAL = "GLOBAL"
    ORGANIZATION = "ORGANIZATION"
    ORGANIZATIONAL_UNIT = "ORGANIZATIONAL_UNIT"
    PROJECT = "PROJECT"


class PermissionScopeItem(BaseModel):
    scope_type: ScopeType
    organization_id: UUID | None = None
    organizational_unit_id: UUID | None = None
    project_id: UUID | None = None


class PrincipalResponse(BaseModel):
    id: UUID | None = Field(default=None, description="None for anonymous principals")
    principal_type: PrincipalType
    authenticated: bool
    status: str
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    organization_ids: list[UUID] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)


class AuthorizationDecisionResponse(BaseModel):
    allowed: bool
    reason: str
    permission: str
    scope: str | None = None
    policy_version: str = "auth-v1"


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=256)
    display_name: str | None = Field(default=None, max_length=256)
    external_subject: str | None = Field(default=None, max_length=512)
    identity_provider: str = Field(default="local", max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    display_name: str | None = None
    identity_provider: str
    status: UserStatus
    roles: list[str] = Field(default_factory=list)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=1, max_length=128)


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str
    status: UserStatus


class OrganizationalUnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=1, max_length=128)


class OrganizationalUnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    code: str
    status: UserStatus


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    status: UserStatus


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None


class RoleAssignmentCreate(BaseModel):
    role_name: str = Field(min_length=1, max_length=128)
    scope_type: ScopeType
    organization_id: UUID | None = None
    organizational_unit_id: UUID | None = None
    project_id: UUID | None = None


class RoleAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    role_id: UUID
    role_name: str | None = None
    scope_type: ScopeType
    organization_id: UUID | None = None
    organizational_unit_id: UUID | None = None
    project_id: UUID | None = None


class ApiClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    scopes: list[str] = Field(min_length=1)
    project_id: UUID | None = None


class ApiClientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    scopes: list[str] = Field(default_factory=list)
    project_id: UUID | None = None
    status: UserStatus


# -- BE-025 administrative control plane --------------------------------------

class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    status: UserStatus | None = None


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
    limit: int
    offset: int
    total: int


class OrganizationalUnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    status: UserStatus | None = None


class OrganizationalUnitListResponse(BaseModel):
    items: list[OrganizationalUnitResponse]
    limit: int
    offset: int
    total: int


class UserStatusUpdate(BaseModel):
    status: UserStatus


class UserListResponse(BaseModel):
    items: list[UserResponse]
    limit: int
    offset: int
    total: int


class RoleAssignmentListResponse(BaseModel):
    items: list[RoleAssignmentResponse]
    limit: int
    offset: int
    total: int


class ProjectScopeUpdate(BaseModel):
    """Set-or-clear semantics: an omitted field keeps its current value; an
    explicit null clears it (GLOBAL authority required, enforced server-side)."""

    organization_id: UUID | None = None
    organizational_unit_id: UUID | None = None


class ProjectOwnershipUpdate(BaseModel):
    owner_id: UUID


class AdminProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    owner_id: UUID
    organization_id: UUID | None = None
    organizational_unit_id: UUID | None = None
