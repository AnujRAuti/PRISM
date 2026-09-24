"""BE-021 Pydantic v2 schemas for disputes.

A dispute is an authorized challenge against an object or assertion.
Resolution is human-governed with an explicit vocabulary — UPHELD, REJECTED,
INCONCLUSIVE, INSUFFICIENT_EVIDENCE — deliberately excluding verdicts like
FRAUD/AUTHENTIC/TRUE/FALSE that collapse evidence state and governance.
"""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DisputeTargetType(str, Enum):
    EVIDENCE = "EVIDENCE"
    EVIDENCE_CLAIM_RELATIONSHIP = "EVIDENCE_CLAIM_RELATIONSHIP"
    CLAIM = "CLAIM"
    EXTERNAL_ASSERTION = "EXTERNAL_ASSERTION"
    FUSION_ASSESSMENT = "FUSION_ASSESSMENT"
    REVIEW_CASE = "REVIEW_CASE"


class DisputeStatus(str, Enum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    ESCALATED = "ESCALATED"


class DisputeResolution(str, Enum):
    UPHELD = "UPHELD"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DisputeCreateRequest(BaseModel):
    target_type: DisputeTargetType
    target_id: UUID
    reason: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=20000)
    initiator_id: UUID | None = Field(
        default=None,
        description="Initiator; defaults to the authenticated principal",
    )


class DisputeAssignRequest(BaseModel):
    assigned_to: UUID
    actor_id: UUID | None = None


class DisputeEscalateRequest(BaseModel):
    escalated_to: UUID
    reason: str = Field(min_length=1, max_length=20000)
    actor_id: UUID | None = None


class DisputeResolveRequest(BaseModel):
    resolution: DisputeResolution
    rationale: str = Field(min_length=1, max_length=20000)
    resolved_by: UUID | None = Field(
        default=None,
        description="Resolver; defaults to the authenticated principal",
    )


class DisputeRejectRequest(BaseModel):
    """Outright dismissal (no adjudication recorded on the row)."""

    rationale: str = Field(min_length=1, max_length=20000)
    actor_id: UUID | None = Field(
        default=None, description="Actor; defaults to the authenticated principal"
    )


class DisputeWithdrawRequest(BaseModel):
    actor_id: UUID | None = None


class DisputeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: str
    target_id: UUID
    project_id: UUID | None = None
    initiator_id: UUID
    reason: str
    description: str | None = None
    status: str
    assigned_to: UUID | None = None
    assigned_at: str | None = None
    escalated_to: UUID | None = None
    escalated_at: str | None = None
    escalation_reason: str | None = None
    resolution: str | None = None
    resolution_rationale: str | None = None
    resolved_by: UUID | None = None
    resolved_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DisputeListResponse(BaseModel):
    items: list[DisputeResponse]
    limit: int
    offset: int
    total: int


class DisputeEventItem(BaseModel):
    id: UUID
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    actor_id: UUID | None = None
    created_at: str | None = None


class DisputeHistoryResponse(BaseModel):
    dispute_id: UUID
    items: list[DisputeEventItem]
    total: int
