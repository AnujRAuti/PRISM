"""BE-013 Pydantic v2 schemas for review cases.

A case initiates a human review workflow because configured intelligence
conditions indicate investigation may be useful. Case creation is never a
determination of truth, fraud, authenticity, or legal sufficiency, and
automatic generation never populates human decision fields.
"""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CaseOrigin(str, Enum):
    SYSTEM_SIGNAL = "SYSTEM_SIGNAL"
    AUTHORIZED_USER = "AUTHORIZED_USER"
    CITIZEN_REPORT = "CITIZEN_REPORT"
    EXTERNAL_SYSTEM = "EXTERNAL_SYSTEM"


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    INVESTIGATING = "INVESTIGATING"
    DECISION_PENDING = "DECISION_PENDING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class CaseDecision(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CaseGenerateRequest(BaseModel):
    policy_version: str | None = Field(
        default=None, description="Pinned policy version; default active v1"
    )


class CaseGenerationResponse(BaseModel):
    result: str = Field(
        description="CASE_CREATED, CASE_ALREADY_EXISTS, or NOT_ELIGIBLE"
    )
    reason: str
    case: "ReviewCaseResponse | None" = None
    generation_run_id: UUID | None = None


class ReviewCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None = None
    claim_id: UUID | None = None
    evidence_id: UUID | None = None
    fusion_run_id: UUID | None = None
    case_generation_run_id: UUID | None = None
    origin: CaseOrigin
    status: CaseStatus
    priority_band: str | None = None
    priority_value: float | None = None
    priority_source: str | None = None
    priority_config_version: str | None = None
    assigned_to: UUID | None = None
    decision: CaseDecision | None = Field(
        default=None, description="Human-supplied only; never automated"
    )
    decision_rationale: str | None = None
    decided_by: UUID | None = None
    escalated_to: UUID | None = None
    escalation_reason: str | None = None


class ReviewCaseListResponse(BaseModel):
    items: list[ReviewCaseResponse]
    limit: int
    offset: int
    total: int


class ReviewCaseEventItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    from_status: CaseStatus | None = None
    to_status: CaseStatus | None = None
    actor_id: UUID | None = None
    created_at: str | None = None


class ReviewCaseHistoryResponse(BaseModel):
    case_id: UUID
    items: list[ReviewCaseEventItem]
    total: int


class CaseAssignmentRequest(BaseModel):
    assigned_to: UUID | None = Field(
        default=None, description="Null unassigns an ASSIGNED case back to OPEN"
    )
    actor_id: UUID | None = Field(
        default=None,
        description="Must equal the authenticated principal; the actor is derived "
                    "from the credential and a conflicting value is refused.",
    )


class CaseDecisionRequest(BaseModel):
    decision: CaseDecision
    rationale: str = Field(min_length=1)
    decided_by: UUID | None = Field(
        default=None,
        description="Must equal the authenticated principal; decisions are attributed "
                    "to the credential, never to this field.",
    )


class CaseEscalationRequest(BaseModel):
    escalated_to: UUID
    reason: str = Field(min_length=1)
    actor_id: UUID | None = Field(
        default=None,
        description="Must equal the authenticated principal; the actor is derived "
                    "from the credential and a conflicting value is refused.",
    )


class CaseGenerationConfigurationCreate(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=256)
    configuration: dict
    enabled: bool = True


class CaseGenerationConfigurationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: str
    name: str
    enabled: bool
    configuration: dict
