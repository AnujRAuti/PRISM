"""BE-017 Pydantic v2 schemas for retention governance.

Retention answers how long a resource is kept and whether it is eligible
for archive or deletion. It never judges truth, fraud, or risk, and all
timestamps are timezone-aware (naive values rejected).
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class RetentionResourceType(str, Enum):
    EVIDENCE = "EVIDENCE"
    ANALYSIS_RESULT = "ANALYSIS_RESULT"
    FUSION_RUN = "FUSION_RUN"
    REVIEW_CASE = "REVIEW_CASE"
    EVIDENCE_REQUEST = "EVIDENCE_REQUEST"
    AUDIT_LEDGER_EVENT = "AUDIT_LEDGER_EVENT"


class RetentionStateValue(str, Enum):
    ACTIVE = "ACTIVE"
    ELIGIBLE_FOR_ARCHIVE = "ELIGIBLE_FOR_ARCHIVE"
    ARCHIVED = "ARCHIVED"
    ELIGIBLE_FOR_DELETION = "ELIGIBLE_FOR_DELETION"
    DELETION_PENDING = "DELETION_PENDING"
    DELETED = "DELETED"


class RetentionScopeType(str, Enum):
    GLOBAL = "GLOBAL"
    ORGANIZATION = "ORGANIZATION"
    ORGANIZATIONAL_UNIT = "ORGANIZATIONAL_UNIT"
    PROJECT = "PROJECT"


class RetentionAnchor(str, Enum):
    INGESTED_AT = "INGESTED_AT"
    CAPTURED_AT = "CAPTURED_AT"
    PROJECT_COMPLETED_AT = "PROJECT_COMPLETED_AT"
    CASE_RESOLVED_AT = "CASE_RESOLVED_AT"
    REQUEST_FULFILLED_AT = "REQUEST_FULFILLED_AT"
    DECISION_AT = "DECISION_AT"
    SUPERSEDED_AT = "SUPERSEDED_AT"
    CUSTOM_POLICY_EVENT = "CUSTOM_POLICY_EVENT"


class PolicyStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    RETIRED = "RETIRED"


class HoldStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class HoldScope(str, Enum):
    RESOURCE = "RESOURCE"
    PROJECT = "PROJECT"
    CASE = "CASE"
    CLAIM = "CLAIM"
    ORGANIZATION = "ORGANIZATION"


class OperationType(str, Enum):
    ARCHIVE = "ARCHIVE"
    RESTORE = "RESTORE"
    DELETE = "DELETE"


class OperationStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PolicyRules(BaseModel):
    retention_days: int = Field(gt=0)
    archive_after_days: int | None = Field(default=None, gt=0)
    anchor: RetentionAnchor
    allow_derived_cleanup: bool = False

    model_config = ConfigDict(extra="forbid")


class PolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=4000)
    resource_type: RetentionResourceType
    scope_type: RetentionScopeType
    organization_id: UUID | None = None
    organizational_unit_id: UUID | None = None
    project_id: UUID | None = None


class PolicyVersionCreate(BaseModel):
    rules: PolicyRules
    effective_from: AwareDatetime | None = None
    effective_until: AwareDatetime | None = None


class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    resource_type: RetentionResourceType
    scope_type: RetentionScopeType
    organization_id: UUID | None = None
    organizational_unit_id: UUID | None = None
    project_id: UUID | None = None


class PolicyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    version: int
    rules: dict
    status: PolicyStatus
    effective_from: datetime | None = None
    effective_until: datetime | None = None


class EvaluateRequest(BaseModel):
    resource_type: RetentionResourceType
    resource_id: UUID


class RetentionEvaluationResponse(BaseModel):
    eligible: bool = Field(description="Deletion eligibility (fail-closed default)")
    archive_eligible: bool
    deletion_eligible: bool
    state: RetentionStateValue
    anchor: str | None = None
    anchor_timestamp: str | None = None
    expiry_timestamp: str | None = None
    policy_id: UUID | None = None
    policy_version: int | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)
    evaluated_at: str


class ResourceRetentionResponse(BaseModel):
    resource_type: RetentionResourceType
    resource_id: UUID
    persisted_state: str | None = None
    evaluation: RetentionEvaluationResponse


class HoldCreate(BaseModel):
    scope: HoldScope
    resource_type: RetentionResourceType | None = None
    resource_id: UUID | None = None
    project_id: UUID | None = None
    claim_id: UUID | None = None
    case_id: UUID | None = None
    organization_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=4000)
    authority: str | None = Field(default=None, max_length=256)
    expires_at: AwareDatetime | None = None


class HoldRelease(BaseModel):
    release_reason: str = Field(min_length=1, max_length=4000)
    released_by: UUID | None = Field(
        default=None,
        description="Must equal the authenticated principal; the releaser is derived "
                    "from the credential and a conflicting value is refused.",
    )


class HoldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scope: HoldScope
    resource_type: str | None = None
    resource_id: UUID | None = None
    project_id: UUID | None = None
    claim_id: UUID | None = None
    case_id: UUID | None = None
    organization_id: UUID | None = None
    reason: str
    authority: str | None = None
    status: HoldStatus
    created_by: UUID | None = None
    released_by: UUID | None = None
    release_reason: str | None = None
    expires_at: datetime | None = None


class HoldListResponse(BaseModel):
    items: list[HoldResponse]
    limit: int
    offset: int
    total: int


class OperationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resource_type: RetentionResourceType
    resource_id: UUID
    operation: OperationType
    status: OperationStatus
    policy_version_id: UUID | None = None
    actor_id: UUID | None = None
    details: dict = Field(default_factory=dict)
    error: str | None = None


class OperationResultResponse(BaseModel):
    result: str
    operation_id: UUID | None = None
    storage_key: str | None = None
    evaluation: dict = Field(default_factory=dict)


class OperationListResponse(BaseModel):
    items: list[OperationResponse]
    limit: int
    offset: int
    total: int
