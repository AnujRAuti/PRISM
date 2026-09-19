"""BE-012 Pydantic v2 schemas for structured explanations.

An explanation describes how an automated fusion result was produced. It
never determines truth, fraud, authenticity, or final human decisions, and
it never uses calibrated-probability language.
"""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExplanationRunStatus(str, Enum):
    GENERATED = "GENERATED"
    FAILED = "FAILED"


class ExplanationTargetType(str, Enum):
    CLAIM = "CLAIM"
    EVIDENCE = "EVIDENCE"


class ExplanationSignalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal_type: str
    state: str
    source: str
    source_entity_id: UUID | None = None
    source_analysis_run_id: UUID | None = None
    raw_value: dict | None = None
    normalized_value: float | None = None
    weight: float
    contribution: float
    method: str
    method_version: str
    details: dict = Field(default_factory=dict)
    included: bool
    reason: str
    lineage: dict = Field(default_factory=dict)


class ExplanationRuleItem(BaseModel):
    rule_id: str
    rule_version: str
    triggered: bool
    result: str
    parameters: dict = Field(default_factory=dict)


class ExplanationUnknownItem(BaseModel):
    signal_type: str
    state: str
    source_entity_id: UUID | None = None
    sentence: str


class ExplanationMethodology(BaseModel):
    fusion_method: str
    fusion_method_version: str
    explanation_method: str
    explanation_method_version: str
    configuration_version: str


class ExplanationSummary(BaseModel):
    text: str
    state_counts: dict[str, int] = Field(default_factory=dict)


class ExplanationResponse(BaseModel):
    explanation_id: UUID | None = Field(
        default=None, description="Set when the explanation was materialized"
    )
    materialized: bool = False
    fusion_run_id: UUID
    target_type: ExplanationTargetType
    target_id: UUID
    integrity_assessment: dict
    review_priority: dict
    methodology: ExplanationMethodology
    configuration: dict
    summary: ExplanationSummary
    signals: list[ExplanationSignalItem]
    rules: list[ExplanationRuleItem]
    priority_trace: dict = Field(default_factory=dict)
    unknowns: list[ExplanationUnknownItem]
    provenance: dict = Field(default_factory=dict)
    generated_at: str | None = None


class ExplanationRunItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fusion_run_id: UUID
    status: ExplanationRunStatus
    method: str
    method_version: str
    error: str | None = None
