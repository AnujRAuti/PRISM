"""BE-021 Pydantic v2 schemas for correction requests.

Corrections apply to mutable CONTEXT of evidence (associations, location,
contextual metadata, descriptive fields) or replace the evidence file with
a new version through normal ingestion. Evidence bytes and cryptographic
identity stay immutable; approval and application remain distinct steps.
"""

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CorrectionTargetType(str, Enum):
    EVIDENCE = "EVIDENCE"


class CorrectionCategory(str, Enum):
    PROJECT_ASSOCIATION = "PROJECT_ASSOCIATION"
    CLAIM_ASSOCIATION = "CLAIM_ASSOCIATION"
    LOCATION_CONTEXT = "LOCATION_CONTEXT"
    CONTEXTUAL_METADATA = "CONTEXTUAL_METADATA"
    DESCRIPTIVE_FIELD = "DESCRIPTIVE_FIELD"
    EVIDENCE_FILE = "EVIDENCE_FILE"


class CorrectionStatus(str, Enum):
    REQUESTED = "REQUESTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class CorrectionCreateRequest(BaseModel):
    target_type: CorrectionTargetType = CorrectionTargetType.EVIDENCE
    target_id: UUID
    category: CorrectionCategory
    requested_change: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Context diff to apply. For EVIDENCE_FILE corrections this must "
            "reference the already-ingested replacement evidence via "
            "'new_evidence_id'."
        ),
    )
    reason: str = Field(min_length=1, max_length=20000)
    requester_id: UUID | None = Field(
        default=None,
        description="Requester; defaults to the authenticated principal",
    )


class CorrectionDecisionRequest(BaseModel):
    """Approve or reject a correction (role-separated from the requester)."""

    rationale: str = Field(min_length=1, max_length=20000)
    resolver_id: UUID | None = Field(
        default=None, description="Resolver; defaults to the authenticated principal"
    )


class CorrectionApplyRequest(BaseModel):
    applied_by: UUID | None = Field(
        default=None, description="Applicant; defaults to the authenticated principal"
    )


class CorrectionCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=20000)
    actor_id: UUID | None = None


class CorrectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: str
    target_id: UUID
    project_id: UUID | None = None
    category: str
    requested_change: dict[str, Any]
    reason: str
    requester_id: UUID
    status: str
    resolver_id: UUID | None = None
    resolution_rationale: str | None = None
    resolved_at: str | None = None
    applied_by: UUID | None = None
    applied_at: str | None = None
    applied_change: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CorrectionListResponse(BaseModel):
    items: list[CorrectionResponse]
    limit: int
    offset: int
    total: int


class CorrectionEventItem(BaseModel):
    id: UUID
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    actor_id: UUID | None = None
    created_at: str | None = None


class CorrectionHistoryResponse(BaseModel):
    correction_id: UUID
    items: list[CorrectionEventItem]
    total: int
