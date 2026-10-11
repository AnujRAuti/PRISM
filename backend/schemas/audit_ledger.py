"""BE-015 Pydantic v2 schemas for the tamper-evident audit ledger.

Verification results are cryptographic integrity statements, never
subjective interpretations of the underlying actions.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence_number: int
    event_type: str
    action: str
    resource_type: str
    resource_id: UUID | None = None
    actor_id: UUID | None = None
    project_id: UUID | None = None
    payload: dict = Field(default_factory=dict)
    event_metadata: dict = Field(default_factory=dict)

    previous_hash: str
    event_hash: str
    hash_algorithm: str
    ledger_version: str
    created_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse]
    limit: int
    offset: int
    total: int


class AuditVerificationFailure(BaseModel):
    sequence_number: int | None = None
    detail: str


class AuditVerificationResponse(BaseModel):
    valid: bool
    checked_events: int
    first_sequence: int | None = None
    last_sequence: int | None = None
    failures: list[str] = Field(default_factory=list)


class AuditLedgerCheckpoint(BaseModel):
    """The durable head digest published outside the ledger (anti-TRUNCATE)."""

    rows: int
    min_sequence: int | None = None
    max_sequence: int | None = None
    tail_event_hash: str | None = None
    tail_previous_hash: str | None = None


class AuditIntegrityClassification(BaseModel):
    """BE-032R F-04: findings labelled against a reviewed historical baseline."""

    status: str
    degraded: bool
    known_historical_gaps: list[str] = Field(default_factory=list)
    new_gaps: list[str] = Field(default_factory=list)
    hard_anomalies: list[str] = Field(default_factory=list)
    baseline_name: str
    baseline_version: int


class AuditAnchoredVerificationResponse(BaseModel):
    """BE-032R F-03: the anchored whole-chain walk with checkpoint + classification."""

    valid: bool
    checked_events: int
    first_sequence: int | None = None
    last_sequence: int | None = None
    failures: list[str] = Field(default_factory=list)
    checkpoint: AuditLedgerCheckpoint
    classification: AuditIntegrityClassification
    writer_policy: str
