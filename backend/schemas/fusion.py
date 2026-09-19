"""BE-011 Pydantic v2 schemas for the Fusion Engine.

Integrity Assessment is an automated evidence-integrity assessment state,
not a final human determination. Review Priority is an operational
prioritization signal, not a fraud probability.
"""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FusionTargetType(str, Enum):
    CLAIM = "CLAIM"
    EVIDENCE = "EVIDENCE"


class FusionRunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AssessmentValue(str, Enum):
    SUPPORTED = "SUPPORTED"
    MIXED = "MIXED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNKNOWN = "UNKNOWN"


class AssessmentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"


class ReviewPriorityLevel(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class FusionSignalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal_type: str
    state: str
    source: str
    source_entity_id: UUID | None = None
    source_analysis_run_id: UUID | None = None
    raw_value: dict | None = None
    normalized_value: float | None = None
    weight: float
    method: str
    method_version: str
    details: dict = Field(default_factory=dict)


class IntegrityAssessmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: FusionTargetType
    target_id: UUID
    assessment_status: AssessmentStatus
    assessment_value: AssessmentValue = Field(
        description="Automated assessment state; not a truth or fraud determination"
    )
    integrity_score: float | None = Field(
        default=None,
        description="Documented weighted aggregation in [-1, 1]; not a probability",
    )
    signal_summary: dict
    method_version: str = "fusion-v1"
    configuration_version: str


class ReviewPriorityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: FusionTargetType
    target_id: UUID
    priority: ReviewPriorityLevel = Field(
        description="Operational review allocation; not a fraud likelihood"
    )
    priority_score: float = Field(
        description="Allocation score in [0, 1]; not a fraud probability"
    )
    signal_summary: dict
    method_version: str = "fusion-v1"
    configuration_version: str


class FusionRunItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: FusionTargetType
    target_id: UUID
    status: FusionRunStatus
    method: str
    method_version: str
    configuration_version: str
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class FusionExecuteRequest(BaseModel):
    configuration_version: str | None = Field(
        default=None, description="Pinned config version; default active v1"
    )


class FusionExecuteResponse(BaseModel):
    run: FusionRunItem
    assessment: IntegrityAssessmentItem
    priority: ReviewPriorityItem
    signals: list[FusionSignalItem]


class FusionLatestResponse(BaseModel):
    run: FusionRunItem
    assessment: IntegrityAssessmentItem
    priority: ReviewPriorityItem
    signals: list[FusionSignalItem]


class FusionRunDetailResponse(BaseModel):
    run: FusionRunItem
    assessment: IntegrityAssessmentItem | None = None
    priority: ReviewPriorityItem | None = None
    signals: list[FusionSignalItem]


class FusionHistoryResponse(BaseModel):
    target_type: FusionTargetType
    target_id: UUID
    items: list[FusionRunItem]
    limit: int
    offset: int
    total: int


class FusionConfigurationCreate(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=256)
    method_version: str = "fusion-v1"
    weights: dict[str, float]
    thresholds: dict[str, float]
    priority: dict
    signals: dict | None = None
    enabled: bool = True


class FusionConfigurationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: str
    name: str
    enabled: bool
    method_version: str
    weights: dict
    thresholds: dict
    priority: dict
    signals: dict
