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
