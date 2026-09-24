"""BE-021 Pydantic v2 schemas for governance operations.

Dependency inspection, direct invalidation, and reprocessing. These are
read/act surfaces over the dependency engine; no new intelligence is
computed here — the engine only marks, records, and delegates.
"""

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.dispute import DisputeTargetType


class GovernanceTargetType(str, Enum):
    """Targets whose derived-intelligence dependencies can be inspected."""

    EVIDENCE = "EVIDENCE"
    EVIDENCE_CLAIM_RELATIONSHIP = "EVIDENCE_CLAIM_RELATIONSHIP"
    CLAIM = "CLAIM"
    EXTERNAL_ASSERTION = "EXTERNAL_ASSERTION"
    FUSION_ASSESSMENT = "FUSION_ASSESSMENT"
    REVIEW_CASE = "REVIEW_CASE"


class InvalidationCause(str, Enum):
    DISPUTE = "DISPUTE"
    CORRECTION = "CORRECTION"
    DIRECT = "DIRECT"


class ReprocessingStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class InvalidationRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=20000)
    invalidated_by: UUID | None = Field(
        default=None,
        description="Actor; defaults to the authenticated principal",
    )
    reprocess: bool = Field(
        default=True,
        description="Create a reprocessing request for affected evidence",
    )


class DependencyNodeItem(BaseModel):
    """One node in the bounded dependency traversal result."""

    kind: str = Field(
        description=(
            "Dependency category: ANALYSIS_JOB, ANALYSIS_RESULT, "
            "FUSION_RUN, EXPLANATION_RUN, INTEGRITY_ASSESSMENT, "
            "GRAPH_RELATIONSHIP, or REVIEW_CASE"
        )
    )
    id: UUID
    staleness: str | None = Field(
        default=None,
        description="Current staleness/assessment/relationship status where applicable",
    )
    depth: int = Field(ge=0, description="Traversal depth from the target (0 = target)")


class DependencyGraphResponse(BaseModel):
    target_type: str
    target_id: UUID
    max_depth: int
    truncated: bool = Field(
        description="True when the bounded traversal stopped before exhausting the graph"
    )
    nodes: list[DependencyNodeItem]
    counts: dict[str, int]


class InvalidationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: str
    target_id: UUID
    project_id: UUID | None = None
    cause: str
    dispute_id: UUID | None = None
    correction_id: UUID | None = None
    reason: str
    invalidated_by: UUID
    affected_analysis: int
    affected_fusion: int
    affected_explanations: int
    affected_relationships: int
    affected_assessments: int
    created_at: str | None = None


class ReprocessRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=20000)
    requested_by: UUID | None = Field(
        default=None,
        description="Requester; defaults to the authenticated principal",
    )


class ReprocessResponse(BaseModel):
    result: str = Field(
        description="REPROCESSING_REQUESTED or REPROCESSING_ALREADY_PENDING"
    )
    reason: str
    reprocessing_request_id: UUID
    evidence_id: UUID
    status: str
    analysis_job_id: UUID | None = None
